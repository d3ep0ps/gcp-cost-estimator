# SPDX-License-Identifier: Apache-2.0

import contextlib
import json
from pathlib import Path
from typing import Any

from gcp_cost_estimator.core.iac.base import IaCParser, get_iac_parser, register_iac_parser
from gcp_cost_estimator.core.model import AttachedResource, Resource, ResourceModel


class TerraformPlanParser(IaCParser):
    """Parses a resolved Terraform plan JSON payload (produced by terraform show -json)."""

    def parse(self, path: str, _options: dict[str, Any] | None = None) -> ResourceModel:
        path_obj = Path(path)
        if path_obj.is_file():
            with path_obj.open(encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(path)

        planned_values = data.get("planned_values", {})
        root_module = planned_values.get("root_module", {})

        raw_resources: list[dict[str, Any]] = []

        def extract_resources_from_module(module: dict[str, Any]) -> None:
            for r in module.get("resources", []):
                raw_resources.append(r)
            for child in module.get("child_modules", []):
                extract_resources_from_module(child)

        extract_resources_from_module(root_module)

        resources: list[Resource] = []
        for raw_res in raw_resources:
            res_type = raw_res.get("type", "")
            if not res_type.startswith("google_"):
                continue

            provider = "gcp"
            address = raw_res.get("address", "")
            values = raw_res.get("values", {})

            if res_type == "google_bigquery_table":
                has_dataset = any(r.get("type") == "google_bigquery_dataset" for r in raw_resources)
                if not has_dataset:
                    import logging

                    logging.getLogger("gcp_cost_estimator").warning(
                        "Orphan BigQuery table '%s' found. "
                        "BigQuery pricing requires parent dataset location.",
                        address,
                    )
                continue

            if res_type == "google_compute_instance":
                service = "compute"
                kind = "gce_instance"
            elif res_type == "google_sql_database_instance":
                service = "sql"
                kind = "cloud_sql_instance"
            elif res_type == "google_storage_bucket":
                service = "storage"
                kind = "gcs_bucket"
            elif res_type == "google_container_cluster":
                service = "container"
                kind = "gke_cluster"
            elif res_type == "google_container_node_pool":
                service = "container"
                kind = "gke_node_pool"
            elif res_type == "google_bigquery_dataset":
                service = "bigquery"
                kind = "bigquery_dataset"
            else:
                parts = res_type.split("_")
                service = parts[1] if len(parts) > 1 else "other"
                kind = res_type

            raw_zone = values.get("zone")
            raw_region = values.get("region")
            raw_location = values.get("location")
            region = None
            assumptions: list[str] = []

            if raw_zone and isinstance(raw_zone, str):
                parts = raw_zone.split("-")
                if len(parts) >= 2:
                    region = "-".join(parts[:-1])
            elif raw_region and isinstance(raw_region, str):
                region = raw_region
            elif raw_location and isinstance(raw_location, str):
                region = raw_location

            attributes: dict[str, Any] = {}
            attached: list[AttachedResource] = []

            if res_type == "google_compute_instance":
                mtype = values.get("machine_type")
                if mtype:
                    attributes["machine_type"] = mtype
                else:
                    attributes["machine_type"] = "e2-medium"
                    assumptions.append("No machine_type specified; defaulted to e2-medium.")

                # Parse scheduling block (preemptible / spot)
                sched_list = values.get("scheduling", [])
                if isinstance(sched_list, list) and sched_list:
                    sched = sched_list[0]
                    if isinstance(sched, dict):
                        preempt = sched.get("preemptible")
                        if preempt is not None:
                            attributes["preemptible"] = preempt

                # Parse boot disk
                boot_disk_list = values.get("boot_disk", [])
                if isinstance(boot_disk_list, list):
                    for bd in boot_disk_list:
                        if not isinstance(bd, dict):
                            continue
                        init_params = bd.get("initialize_params", [])
                        if isinstance(init_params, list) and init_params:
                            ip = init_params[0]
                            if isinstance(ip, dict):
                                dsize = ip.get("size") or ip.get("size_gb") or 10
                                dtype = ip.get("type") or "pd-standard"
                                disk_kind = (
                                    "ssd_persistent_disk"
                                    if "ssd" in str(dtype).lower()
                                    else "pd_persistent_disk"
                                )
                                attached.append(
                                    AttachedResource(
                                        kind=disk_kind,
                                        quantity=1,
                                        attributes={"size_gb": int(dsize)},
                                    )
                                )
            elif res_type == "google_sql_database_instance":
                db_ver = values.get("database_version")
                if db_ver:
                    attributes["database_version"] = db_ver

                settings_list = values.get("settings", [])
                if isinstance(settings_list, list) and settings_list:
                    settings = settings_list[0]
                    if isinstance(settings, dict):
                        for field in ("tier", "edition", "availability_type", "disk_type"):
                            val = settings.get(field)
                            if val is not None:
                                attributes[field] = val

                        disk_size = settings.get("disk_size")
                        if disk_size is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                attributes["disk_size_gb"] = int(disk_size)

                        backup_config_list = settings.get("backup_configuration", [])
                        if isinstance(backup_config_list, list) and backup_config_list:
                            backup_config = backup_config_list[0]
                            if isinstance(backup_config, dict):
                                backup_enabled = backup_config.get("enabled")
                                if backup_enabled is not None:
                                    attributes["backup_enabled"] = bool(backup_enabled)
            elif res_type in {"google_container_cluster", "google_container_node_pool"}:
                autopilot = values.get("enable_autopilot")
                if autopilot is not None:
                    attributes["enable_autopilot"] = bool(autopilot)

                node_count = values.get("node_count") or values.get("initial_node_count")
                if node_count is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        attributes["node_count"] = int(node_count)

                node_configs = values.get("node_config", [])
                if isinstance(node_configs, list) and node_configs:
                    nc = node_configs[0]
                    if isinstance(nc, dict):
                        mtype = nc.get("machine_type")
                        if mtype:
                            attributes["machine_type"] = mtype
                        disk_size = nc.get("disk_size_gb")
                        if disk_size is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                attributes["disk_size_gb"] = int(disk_size)
                        disk_type = nc.get("disk_type")
                        if disk_type:
                            attributes["disk_type"] = disk_type
            else:
                for k, v in values.items():
                    if v is not None:
                        attributes[k] = v

            resources.append(
                Resource(
                    provider=provider,
                    resource_id=address,
                    service=service,
                    kind=kind,
                    region=region,
                    attributes=attributes,
                    attached=attached,
                    quantity=1,
                    assumptions=assumptions,
                )
            )

        return ResourceModel(resources=resources)


register_iac_parser("terraform-plan", TerraformPlanParser)


def parse_terraform(path: str, mode: str = "auto") -> ResourceModel:
    """Convenience dispatcher to parse Terraform directory or plan JSON.

    If mode is "plan", parses as a plan JSON file.
    If mode is "hcl", parses as static HCL directory.
    If mode is "auto", inspects path:
      - If it is a file ending in .json or contains plan structure, parses as plan JSON.
      - Otherwise, parses as HCL directory.
    """
    resolved_mode = mode
    if mode == "auto":
        if Path(path).is_file() and (path.endswith(".json") or "plan" in path.lower()):
            resolved_mode = "plan"
        else:
            resolved_mode = "hcl"

    if resolved_mode == "plan":
        parser = get_iac_parser("terraform-plan")
    else:
        parser = get_iac_parser("terraform")

    return parser.parse(path)
