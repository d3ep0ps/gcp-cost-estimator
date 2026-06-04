# SPDX-License-Identifier: Apache-2.0

import contextlib
import re
from pathlib import Path
from typing import Any

import hcl2  # type: ignore[import-untyped]

from gcp_cost_estimator.core.iac.base import IaCParser, register_iac_parser
from gcp_cost_estimator.core.model import AttachedResource, Resource, ResourceModel


def _extract_scalar(val: Any) -> Any:
    if isinstance(val, list):
        if len(val) == 1:
            return _extract_scalar(val[0])
        if len(val) == 0:
            return None
    if isinstance(val, str):
        return val.strip("\"'")
    return val


def _is_unresolved(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    return bool(re.search(r"\$\{.*?\}", val) or val.startswith("var.") or "count." in val)


class TerraformHclParser(IaCParser):
    """Parses static Terraform HCL files in a directory to extract resources."""

    def parse(self, path: str, _options: dict[str, Any] | None = None) -> ResourceModel:
        path_obj = Path(path)
        if not path_obj.is_dir():
            msg = f"Path '{path}' is not a directory. Terraform HCL parser requires a directory."
            raise ValueError(msg)

        # Find all .tf files
        tf_files = [f for f in path_obj.iterdir() if f.is_file() and f.suffix == ".tf"]

        merged_config: dict[str, Any] = {}
        for fpath in tf_files:
            try:
                with fpath.open(encoding="utf-8") as f:
                    config = hcl2.load(f)
                    for key, val in config.items():
                        if key not in merged_config:
                            merged_config[key] = []
                        if isinstance(val, list):
                            merged_config[key].extend(val)
            except Exception:
                # Suppress parse errors for individual files to be resilient
                pass

        # Build variable defaults lookup
        var_defaults: dict[str, Any] = {}
        for var_dict in merged_config.get("variable", []):
            if isinstance(var_dict, dict):
                for var_name, var_info in var_dict.items():
                    clean_var_name = var_name.strip("\"'")
                    if isinstance(var_info, dict) and "default" in var_info:
                        var_defaults[clean_var_name] = _extract_scalar(var_info["default"])

        def resolve_value(val: Any) -> Any:
            scalar = _extract_scalar(val)
            if isinstance(scalar, str):
                match = re.match(r"^\$?\{?var\.([a-zA-Z0-9_-]+)\}?$", scalar)
                if match:
                    var_name = match.group(1)
                    if var_name in var_defaults:
                        return var_defaults[var_name]
            return scalar

        resources: list[Resource] = []

        for res_dict in merged_config.get("resource", []):
            if not isinstance(res_dict, dict):
                continue
            for res_type, instances in res_dict.items():
                res_type_clean = res_type.strip("\"'")
                if not isinstance(instances, dict):
                    continue
                for res_name, res_config in instances.items():
                    res_name_clean = res_name.strip("\"'")
                    if not isinstance(res_config, dict):
                        continue

                    # Only process Google Cloud resources in this provider mapping
                    if not res_type_clean.startswith("google_"):
                        continue

                    provider = "gcp"

                    if res_type_clean == "google_bigquery_table":
                        has_dataset = False
                        for r_dict in merged_config.get("resource", []):
                            if isinstance(r_dict, dict) and "google_bigquery_dataset" in r_dict:
                                has_dataset = True
                                break
                        if not has_dataset:
                            import logging

                            logging.getLogger("gcp_cost_estimator").warning(
                                "Orphan BigQuery table '%s' found. "
                                "BigQuery pricing requires parent dataset location.",
                                res_name_clean,
                            )
                        continue

                    if res_type_clean == "google_compute_instance":
                        service = "compute"
                        kind = "gce_instance"
                    elif res_type_clean == "google_sql_database_instance":
                        service = "sql"
                        kind = "cloud_sql_instance"
                    elif res_type_clean == "google_storage_bucket":
                        service = "storage"
                        kind = "gcs_bucket"
                    elif res_type_clean == "google_container_cluster":
                        service = "container"
                        kind = "gke_cluster"
                    elif res_type_clean == "google_container_node_pool":
                        service = "container"
                        kind = "gke_node_pool"
                    elif res_type_clean == "google_bigquery_dataset":
                        service = "bigquery"
                        kind = "bigquery_dataset"
                    else:
                        parts = res_type_clean.split("_")
                        service = parts[1] if len(parts) > 1 else "other"
                        kind = res_type_clean

                    raw_zone = resolve_value(res_config.get("zone"))
                    raw_region = resolve_value(res_config.get("region"))
                    raw_location = resolve_value(res_config.get("location"))

                    region = None
                    assumptions: list[str] = []

                    if raw_zone and isinstance(raw_zone, str):
                        if _is_unresolved(raw_zone):
                            assumptions.append(f"Unresolved zone reference: '{raw_zone}'")
                        else:
                            parts = raw_zone.split("-")
                            if len(parts) >= 2:
                                region = "-".join(parts[:-1])
                    elif raw_region and isinstance(raw_region, str):
                        if _is_unresolved(raw_region):
                            assumptions.append(f"Unresolved region reference: '{raw_region}'")
                        else:
                            region = raw_region
                    elif raw_location and isinstance(raw_location, str):
                        if _is_unresolved(raw_location):
                            assumptions.append(f"Unresolved region reference: '{raw_location}'")
                        else:
                            region = raw_location

                    quantity = 1
                    raw_count = resolve_value(res_config.get("count"))
                    if raw_count is not None:
                        if _is_unresolved(raw_count):
                            assumptions.append(
                                "Unresolved count variable reference: default to quantity 1. "
                                f"Count reference: '{raw_count}'"
                            )
                        else:
                            try:
                                quantity = int(raw_count)
                            except ValueError, TypeError:
                                assumptions.append(
                                    f"Invalid count value '{raw_count}': default to quantity 1."
                                )

                    attributes: dict[str, Any] = {}
                    attached: list[AttachedResource] = []

                    if res_type_clean == "google_compute_instance":
                        mtype = resolve_value(res_config.get("machine_type"))
                        if mtype:
                            attributes["machine_type"] = mtype
                            if _is_unresolved(mtype):
                                assumptions.append(f"Unresolved attribute machine_type: '{mtype}'")
                        else:
                            assumptions.append("No machine_type specified; fallback to e2-medium.")
                            attributes["machine_type"] = "e2-medium"

                        # Parse scheduling block (preemptible / spot)
                        sched_list = res_config.get("scheduling", [])
                        if isinstance(sched_list, list) and sched_list:
                            sched = sched_list[0]
                            if isinstance(sched, dict):
                                preempt = resolve_value(sched.get("preemptible"))
                                if preempt is not None:
                                    attributes["preemptible"] = preempt

                        # Parse boot disks
                        boot_disks = res_config.get("boot_disk", [])
                        if isinstance(boot_disks, list):
                            for bd in boot_disks:
                                if not isinstance(bd, dict):
                                    continue
                                init_params_list = bd.get("initialize_params", [])
                                if isinstance(init_params_list, list) and init_params_list:
                                    ip = init_params_list[0]
                                    if isinstance(ip, dict):
                                        dsize = (
                                            resolve_value(ip.get("size"))
                                            or resolve_value(ip.get("size_gb"))
                                            or 10
                                        )
                                        dtype = resolve_value(ip.get("type")) or "pd-standard"

                                        disk_kind = (
                                            "ssd_persistent_disk"
                                            if "ssd" in str(dtype).lower()
                                            else "pd_persistent_disk"
                                        )
                                        try:
                                            size_val = int(dsize)
                                        except ValueError, TypeError:
                                            size_val = 10
                                            assumptions.append(
                                                f"Unresolved or invalid boot disk size '{dsize}': "
                                                "default to 10 GB."
                                            )

                                        attached.append(
                                            AttachedResource(
                                                kind=disk_kind,
                                                quantity=1,
                                                attributes={"size_gb": size_val},
                                            )
                                        )
                    elif res_type_clean == "google_sql_database_instance":
                        db_ver = resolve_value(res_config.get("database_version"))
                        if db_ver:
                            attributes["database_version"] = db_ver
                            if _is_unresolved(db_ver):
                                assumptions.append(
                                    f"Unresolved attribute database_version: '{db_ver}'"
                                )

                        settings_list = res_config.get("settings", [])
                        if isinstance(settings_list, list) and settings_list:
                            settings = settings_list[0]
                            if isinstance(settings, dict):
                                for field in ("tier", "edition", "availability_type", "disk_type"):
                                    val = resolve_value(settings.get(field))
                                    if val is not None:
                                        attributes[field] = val
                                        if _is_unresolved(val):
                                            assumptions.append(
                                                f"Unresolved attribute {field}: '{val}'"
                                            )

                                disk_size = resolve_value(settings.get("disk_size"))
                                if disk_size is not None:
                                    try:
                                        if _is_unresolved(disk_size):
                                            attributes["disk_size_gb"] = disk_size
                                            assumptions.append(
                                                f"Unresolved attribute disk_size: '{disk_size}'"
                                            )
                                        else:
                                            attributes["disk_size_gb"] = int(disk_size)
                                    except ValueError, TypeError:
                                        pass

                                backup_config_list = settings.get("backup_configuration", [])
                                if isinstance(backup_config_list, list) and backup_config_list:
                                    backup_config = backup_config_list[0]
                                    if isinstance(backup_config, dict):
                                        backup_enabled = resolve_value(backup_config.get("enabled"))
                                        if backup_enabled is not None:
                                            attributes["backup_enabled"] = bool(backup_enabled)
                    elif res_type_clean in {
                        "google_container_cluster",
                        "google_container_node_pool",
                    }:
                        autopilot_list = res_config.get("enable_autopilot")
                        if autopilot_list is not None:
                            val = resolve_value(autopilot_list)
                            if val is not None:
                                attributes["enable_autopilot"] = bool(val)

                        node_count = resolve_value(res_config.get("node_count")) or resolve_value(
                            res_config.get("initial_node_count")
                        )
                        if node_count is not None:
                            if _is_unresolved(node_count):
                                attributes["node_count"] = node_count
                                assumptions.append(
                                    f"Unresolved attribute node_count: '{node_count}'"
                                )
                            else:
                                with contextlib.suppress(ValueError, TypeError):
                                    attributes["node_count"] = int(node_count)

                        node_configs = res_config.get("node_config", [])
                        if isinstance(node_configs, list) and node_configs:
                            nc = node_configs[0]
                            if isinstance(nc, dict):
                                mtype = resolve_value(nc.get("machine_type"))
                                if mtype:
                                    attributes["machine_type"] = mtype
                                    if _is_unresolved(mtype):
                                        assumptions.append(
                                            f"Unresolved attribute machine_type: '{mtype}'"
                                        )

                                disk_size = resolve_value(nc.get("disk_size_gb"))
                                if disk_size is not None:
                                    if _is_unresolved(disk_size):
                                        attributes["disk_size_gb"] = disk_size
                                        assumptions.append(
                                            f"Unresolved attribute disk_size_gb: '{disk_size}'"
                                        )
                                    else:
                                        with contextlib.suppress(ValueError, TypeError):
                                            attributes["disk_size_gb"] = int(disk_size)

                                disk_type = resolve_value(nc.get("disk_type"))
                                if disk_type:
                                    attributes["disk_type"] = disk_type
                                    if _is_unresolved(disk_type):
                                        assumptions.append(
                                            f"Unresolved attribute disk_type: '{disk_type}'"
                                        )
                    else:
                        for k, v in res_config.items():
                            resolved_v = resolve_value(v)
                            if resolved_v is not None:
                                attributes[k] = resolved_v

                    resources.append(
                        Resource(
                            provider=provider,
                            resource_id=f"{res_type_clean}.{res_name_clean}",
                            service=service,
                            kind=kind,
                            region=region,
                            attributes=attributes,
                            attached=attached,
                            quantity=quantity,
                            assumptions=assumptions,
                        )
                    )

        return ResourceModel(resources=resources)


register_iac_parser("terraform", TerraformHclParser)
