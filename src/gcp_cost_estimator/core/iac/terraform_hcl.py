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

                    from gcp_cost_estimator.core.iac.gcp import RESOURCE_TYPE_MAP
                    from gcp_cost_estimator.core.iac.gcp.context import ParserContext

                    if res_type_clean in RESOURCE_TYPE_MAP:
                        parser_fn = RESOURCE_TYPE_MAP[res_type_clean]
                        ctx = ParserContext(
                            attrs=res_config,
                            resolve=resolve_value,
                            is_unresolved=_is_unresolved,
                            assumptions=[],
                        )
                        labels = resolve_value(res_config.get("labels")) or {}
                        if not isinstance(labels, dict):
                            labels = {}
                        res = parser_fn(f"{res_type_clean}.{res_name_clean}", ctx, labels)
                        resources.append(res)
                        continue

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
                    elif res_type_clean == "google_cloud_run_v2_service":
                        service = "run"
                        kind = "cloud_run_service"
                    elif res_type_clean == "google_cloud_run_v2_job":
                        service = "run"
                        kind = "cloud_run_job"
                    elif res_type_clean in (
                        "google_cloudfunctions_function",
                        "google_cloudfunctions2_function",
                    ):
                        service = "functions"
                        kind = "cloud_function"
                    elif res_type_clean == "google_app_engine_standard_app_version":
                        service = "appengine"
                        kind = "app_engine_standard_version"
                    elif res_type_clean == "google_app_engine_flexible_app_version":
                        service = "appengine"
                        kind = "app_engine_flexible_version"
                    elif res_type_clean == "google_spanner_instance":
                        service = "spanner"
                        kind = "spanner_instance"
                    elif res_type_clean == "google_firestore_database":
                        service = "firestore"
                        kind = "firestore_database"
                    elif res_type_clean == "google_redis_instance":
                        service = "memorystore"
                        kind = "redis_instance"
                    elif res_type_clean == "google_memorystore_instance":
                        service = "memorystore"
                        kind = "memorystore_instance"
                    elif res_type_clean == "google_bigtable_instance":
                        service = "bigtable"
                        kind = "bigtable_instance"
                    elif res_type_clean == "google_alloydb_cluster":
                        service = "alloydb"
                        kind = "alloydb_cluster"
                    elif res_type_clean == "google_alloydb_instance":
                        service = "alloydb"
                        kind = "alloydb_instance"
                    elif res_type_clean in (
                        "google_compute_backend_bucket",
                        "google_compute_backend_service",
                    ) and res_config.get("cdn_policy"):
                        service = "cdn"
                        kind = "cloud_cdn_backend"
                    elif res_type_clean == "google_app_engine_application":
                        service = "appengine"
                        kind = "google_app_engine_application"
                    elif res_type_clean == "google_dns_managed_zone":
                        service = "dns"
                        kind = "dns_managed_zone"
                    elif res_type_clean == "google_compute_router_nat":
                        service = "nat"
                        kind = "nat_gateway"
                    elif res_type_clean == "google_compute_address":
                        service = "vpc"
                        kind = "compute_address"
                    elif res_type_clean == "google_compute_security_policy":
                        service = "armor"
                        kind = "compute_security_policy"
                    elif res_type_clean == "google_pubsub_topic":
                        service = "pubsub"
                        kind = "pubsub_topic"
                    elif res_type_clean == "google_pubsub_subscription":
                        service = "pubsub"
                        kind = "pubsub_subscription"
                    elif res_type_clean == "google_pubsub_lite_topic":
                        service = "pubsub"
                        kind = "pubsub_lite_topic"
                    elif res_type_clean == "google_pubsub_lite_subscription":
                        service = "pubsub"
                        kind = "pubsub_lite_subscription"
                    elif res_type_clean == "google_dataflow_job":
                        service = "dataflow"
                        kind = "dataflow_job"
                    elif res_type_clean == "google_dataproc_cluster":
                        service = "dataproc"
                        kind = "dataproc_cluster"
                    elif res_type_clean == "google_dataproc_serverless_batch":
                        service = "dataproc"
                        kind = "dataproc_serverless_batch"
                    elif res_type_clean == "google_filestore_instance":
                        service = "filestore"
                        kind = "google_filestore_instance"
                    elif res_type_clean == "google_vertex_ai_endpoint":
                        service = "vertex"
                        kind = "google_vertex_ai_endpoint"
                    elif res_type_clean == "google_artifact_registry_repository":
                        service = "artifact"
                        kind = "google_artifact_registry_repository"
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

                    if kind in (
                        "dns_managed_zone",
                        "compute_security_policy",
                        "pubsub_topic",
                        "pubsub_subscription",
                    ):
                        region = "global"

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

                    if kind == "cloud_cdn_backend":
                        attributes["cdn_enabled"] = True

                    if kind == "dns_managed_zone":
                        visibility = resolve_value(res_config.get("visibility"))
                        if visibility:
                            attributes["visibility"] = visibility
                        else:
                            attributes["visibility"] = "public"

                    if kind == "nat_gateway":
                        allocate_option = resolve_value(res_config.get("nat_ip_allocate_option"))
                        if allocate_option:
                            attributes["nat_ip_allocate_option"] = allocate_option

                    if kind == "compute_address":
                        addr_type = resolve_value(res_config.get("address_type"))
                        if addr_type:
                            attributes["address_type"] = addr_type
                        purpose = resolve_value(res_config.get("purpose"))
                        if purpose:
                            attributes["purpose"] = purpose

                    if kind == "compute_security_policy":
                        rules = res_config.get("rule", [])
                        if isinstance(rules, dict):
                            attributes["rule_count"] = 1
                        elif isinstance(rules, list):
                            attributes["rule_count"] = len(rules)
                        else:
                            attributes["rule_count"] = 0

                    if kind == "pubsub_subscription":
                        retain = resolve_value(res_config.get("retain_acked_messages"))
                        if retain is not None:
                            attributes["retain_acked_messages"] = retain

                    if kind == "dataflow_job":
                        mtype = resolve_value(res_config.get("machine_type"))
                        if mtype:
                            attributes["machine_type"] = mtype
                        max_w = resolve_value(res_config.get("max_workers"))
                        if max_w is not None:
                            attributes["max_workers"] = max_w

                    if kind == "dataproc_cluster":
                        # Master config
                        master_configs = res_config.get("master_config", [])
                        if isinstance(master_configs, dict):
                            master_configs = [master_configs]
                        if isinstance(master_configs, list) and master_configs:
                            mc = master_configs[0]
                            if isinstance(mc, dict):
                                num_inst = mc.get("num_instances")
                                m_type = mc.get("machine_type")
                                if num_inst is not None:
                                    attributes["num_master_nodes"] = resolve_value(num_inst)
                                if m_type is not None:
                                    attributes["master_machine_type"] = resolve_value(m_type)

                        # Worker config
                        worker_configs = res_config.get("worker_config", [])
                        if isinstance(worker_configs, dict):
                            worker_configs = [worker_configs]
                        if isinstance(worker_configs, list) and worker_configs:
                            wc = worker_configs[0]
                            if isinstance(wc, dict):
                                num_inst = wc.get("num_instances")
                                w_type = wc.get("machine_type")
                                if num_inst is not None:
                                    attributes["num_worker_nodes"] = resolve_value(num_inst)
                                if w_type is not None:
                                    attributes["worker_machine_type"] = resolve_value(w_type)

                        # Preemptible worker config
                        preempt_configs = res_config.get("preemptible_worker_config", [])
                        if isinstance(preempt_configs, dict):
                            preempt_configs = [preempt_configs]
                        if isinstance(preempt_configs, list) and preempt_configs:
                            pc = preempt_configs[0]
                            if isinstance(pc, dict):
                                num_inst = pc.get("num_instances")
                                if num_inst is not None:
                                    attributes["num_preemptible_nodes"] = resolve_value(num_inst)

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
                    elif res_type_clean == "google_cloud_run_v2_service":
                        template_list = res_config.get("template", [])
                        if not isinstance(template_list, list):
                            template_list = [template_list]
                        for template in template_list:
                            if not isinstance(template, dict):
                                continue
                            scaling_list = template.get("scaling", [])
                            if not isinstance(scaling_list, list):
                                scaling_list = [scaling_list]
                            for scaling in scaling_list:
                                if not isinstance(scaling, dict):
                                    continue
                                for field in ("min_instance_count", "max_instance_count"):
                                    val = resolve_value(scaling.get(field))
                                    if val is not None:
                                        if _is_unresolved(val):
                                            assumptions.append(
                                                f"Unresolved attribute {field}: '{val}'"
                                            )
                                        else:
                                            with contextlib.suppress(ValueError, TypeError):
                                                attributes[field] = int(val)
                            containers_list = template.get("containers", [])
                            if not isinstance(containers_list, list):
                                containers_list = [containers_list]
                            for container in containers_list:
                                if not isinstance(container, dict):
                                    continue
                                resources_list = container.get("resources", [])
                                if not isinstance(resources_list, list):
                                    resources_list = [resources_list]
                                for res_conf in resources_list:
                                    if not isinstance(res_conf, dict):
                                        continue
                                    cpu_idle_val = resolve_value(res_conf.get("cpu_idle"))
                                    if cpu_idle_val is not None:
                                        if _is_unresolved(cpu_idle_val):
                                            assumptions.append(
                                                f"Unresolved attribute cpu_idle: '{cpu_idle_val}'"
                                            )
                                        else:
                                            attributes["cpu_idle"] = str(cpu_idle_val).lower() in {
                                                "true",
                                                "1",
                                                "yes",
                                            }
                                    limits_list = res_conf.get("limits", [])
                                    if not isinstance(limits_list, list):
                                        limits_list = [limits_list]
                                    for limits in limits_list:
                                        if not isinstance(limits, dict):
                                            continue
                                        for limit_key in ("cpu", "memory"):
                                            val = resolve_value(limits.get(limit_key))
                                            if val is not None:
                                                attributes[limit_key] = val
                                                if _is_unresolved(val):
                                                    assumptions.append(
                                                        f"Unresolved attribute {limit_key}: '{val}'"
                                                    )

                    elif res_type_clean == "google_cloud_run_v2_job":
                        template_list = res_config.get("template", [])
                        if not isinstance(template_list, list):
                            template_list = [template_list]
                        for template in template_list:
                            if not isinstance(template, dict):
                                continue
                            sub_template_list = template.get("template", [])
                            if not isinstance(sub_template_list, list):
                                sub_template_list = [sub_template_list]
                            for sub_template in sub_template_list:
                                if not isinstance(sub_template, dict):
                                    continue
                                containers_list = sub_template.get("containers", [])
                                if not isinstance(containers_list, list):
                                    containers_list = [containers_list]
                                for container in containers_list:
                                    if not isinstance(container, dict):
                                        continue
                                    resources_list = container.get("resources", [])
                                    if not isinstance(resources_list, list):
                                        resources_list = [resources_list]
                                    for res_conf in resources_list:
                                        if not isinstance(res_conf, dict):
                                            continue
                                        limits_list = res_conf.get("limits", [])
                                        if not isinstance(limits_list, list):
                                            limits_list = [limits_list]
                                        for limits in limits_list:
                                            if not isinstance(limits, dict):
                                                continue
                                            for limit_key in ("cpu", "memory"):
                                                val = resolve_value(limits.get(limit_key))
                                                if val is not None:
                                                    attributes[limit_key] = val
                                                    if _is_unresolved(val):
                                                        assumptions.append(
                                                            f"Unresolved attribute {limit_key}: "
                                                            f"'{val}'"
                                                        )
                    elif res_type_clean == "google_cloudfunctions_function":
                        attributes["generation"] = "1st_gen"
                        for field in ("available_memory_mb", "min_instances"):
                            val = resolve_value(res_config.get(field))
                            if val is not None:
                                attributes[field] = val
                                if _is_unresolved(val):
                                    assumptions.append(f"Unresolved attribute {field}: '{val}'")

                    elif res_type_clean == "google_cloudfunctions2_function":
                        attributes["generation"] = "2nd_gen"
                        sc_list = res_config.get("service_config", [])
                        if not isinstance(sc_list, list):
                            sc_list = [sc_list]
                        for sc in sc_list:
                            if not isinstance(sc, dict):
                                continue
                            for field in (
                                "available_memory",
                                "available_cpu",
                                "min_instance_count",
                                "max_instance_count",
                            ):
                                val = resolve_value(sc.get(field))
                                if val is not None:
                                    attributes[field] = val
                                    if _is_unresolved(val):
                                        assumptions.append(f"Unresolved attribute {field}: '{val}'")

                    elif res_type_clean == "google_app_engine_standard_app_version":
                        iclass = resolve_value(res_config.get("instance_class"))
                        if iclass:
                            attributes["instance_class"] = iclass
                            if _is_unresolved(iclass):
                                assumptions.append(
                                    f"Unresolved attribute instance_class: '{iclass}'"
                                )

                        # Extract scaling block info
                        for scaling_type in (
                            "automatic_scaling",
                            "basic_scaling",
                            "manual_scaling",
                        ):
                            scaling_list = res_config.get(scaling_type, [])
                            if isinstance(scaling_list, list) and scaling_list:
                                attributes["scaling_type"] = scaling_type
                                scaling_blk = scaling_list[0]
                                if isinstance(scaling_blk, dict):
                                    for k, v in scaling_blk.items():
                                        resolved_v = resolve_value(v)
                                        if resolved_v is not None:
                                            attributes[f"{scaling_type}_{k}"] = resolved_v
                                            if _is_unresolved(resolved_v):
                                                assumptions.append(
                                                    f"Unresolved attribute {scaling_type}_{k}: "
                                                    f"'{resolved_v}'"
                                                )

                    elif res_type_clean == "google_app_engine_flexible_app_version":
                        resources_blk = res_config.get("resources")
                        if isinstance(resources_blk, list) and resources_blk:
                            resources_blk = resources_blk[0]
                        if isinstance(resources_blk, dict):
                            for field in ("cpu", "memory_gb", "disk_gb"):
                                val = resolve_value(resources_blk.get(field))
                                if val is not None:
                                    attributes[field] = val
                                    if _is_unresolved(val):
                                        assumptions.append(f"Unresolved attribute {field}: '{val}'")
                        else:
                            assumptions.append("No resources configuration found; using defaults.")

                    elif res_type_clean == "google_spanner_instance":
                        for field in ("config", "num_nodes", "processing_units", "edition"):
                            val = resolve_value(res_config.get(field))
                            if val is not None:
                                attributes[field] = val
                                if _is_unresolved(val):
                                    assumptions.append(f"Unresolved attribute {field}: '{val}'")
                        if not region:
                            config_val = attributes.get("config")
                            if config_val and isinstance(config_val, str):
                                if config_val.startswith("regional-"):
                                    region = config_val[len("regional-") :]
                                elif config_val.startswith("nam"):
                                    region = "us-central1"
                                elif config_val.startswith("eur"):
                                    region = "europe-west1"
                                elif config_val.startswith("asia"):
                                    region = "asia-east1"

                    elif res_type_clean == "google_firestore_database":
                        db_type = resolve_value(res_config.get("type"))
                        if db_type is not None:
                            attributes["database_type"] = db_type
                            if _is_unresolved(db_type):
                                assumptions.append(f"Unresolved attribute type: '{db_type}'")
                        loc_id = resolve_value(res_config.get("location_id"))
                        if loc_id is not None:
                            if not _is_unresolved(loc_id):
                                region = loc_id
                            else:
                                assumptions.append(f"Unresolved attribute location_id: '{loc_id}'")

                    elif res_type_clean == "google_redis_instance":
                        for field in ("memory_size_gb", "tier", "region", "redis_version"):
                            val = resolve_value(res_config.get(field))
                            if val is not None:
                                attributes[field] = val
                                if _is_unresolved(val):
                                    assumptions.append(f"Unresolved attribute {field}: '{val}'")
                        if not region and attributes.get("region"):
                            region = attributes["region"]

                    elif res_type_clean == "google_memorystore_instance":
                        fields = ("instance_id", "location", "shard_count", "node_type", "mode")
                        for field in fields:
                            val = resolve_value(res_config.get(field))
                            if val is not None:
                                attributes[field] = val
                                if _is_unresolved(val):
                                    assumptions.append(f"Unresolved attribute {field}: '{val}'")
                        if not region and attributes.get("location"):
                            region = attributes["location"]

                    elif res_type_clean == "google_bigtable_instance":
                        inst_type = resolve_value(res_config.get("instance_type"))
                        if inst_type is not None:
                            attributes["instance_type"] = inst_type
                            if _is_unresolved(inst_type):
                                msg = f"Unresolved attribute instance_type: '{inst_type}'"
                                assumptions.append(msg)

                        clusters_raw = res_config.get("cluster")
                        if clusters_raw:
                            if not isinstance(clusters_raw, list):
                                clusters_raw = [clusters_raw]
                            clusters_list = []
                            for cl in clusters_raw:
                                if isinstance(cl, dict):
                                    cl_dict = {}
                                    for k, v in cl.items():
                                        resolved_v = resolve_value(v)
                                        cl_dict[k] = resolved_v
                                        if resolved_v is not None and _is_unresolved(resolved_v):
                                            msg = (
                                                f"Unresolved attribute cluster_{k}: '{resolved_v}'"
                                            )
                                            assumptions.append(msg)
                                    clusters_list.append(cl_dict)
                            attributes["clusters"] = clusters_list

                        if clusters_raw and not region:
                            first_cl = clusters_raw[0]
                            if isinstance(first_cl, dict):
                                first_zone = resolve_value(first_cl.get("zone"))
                                if first_zone and not _is_unresolved(first_zone):
                                    region = re.sub(r"-[a-z]$", "", str(first_zone).strip()).lower()

                    elif res_type_clean == "google_alloydb_cluster":
                        initial_user = res_config.get("initial_user")
                        if initial_user:
                            if isinstance(initial_user, list) and initial_user:
                                initial_user_blk = initial_user[0]
                            else:
                                initial_user_blk = initial_user
                            if isinstance(initial_user_blk, dict):
                                initial_user_blk_copy = dict(initial_user_blk)
                                initial_user_blk_copy.pop("password", None)
                                attributes["initial_user"] = initial_user_blk_copy

                        for k, v in res_config.items():
                            if k == "initial_user":
                                continue
                            resolved_v = resolve_value(v)
                            if resolved_v is not None:
                                attributes[k] = resolved_v

                    elif res_type_clean == "google_alloydb_instance":
                        itype = resolve_value(res_config.get("instance_type"))
                        if itype is not None:
                            attributes["instance_type"] = itype
                        if _is_unresolved(itype):
                            assumptions.append(f"Unresolved attribute instance_type: '{itype}'")

                        mconfig = res_config.get("machine_config")
                        if mconfig:
                            if isinstance(mconfig, list) and mconfig:
                                mconfig_blk = mconfig[0]
                            else:
                                mconfig_blk = mconfig
                            if isinstance(mconfig_blk, dict):
                                cpu_count = resolve_value(mconfig_blk.get("cpu_count"))
                                if cpu_count is not None:
                                    attributes["cpu_count"] = cpu_count
                                    if _is_unresolved(cpu_count):
                                        msg = f"Unresolved attribute cpu_count: '{cpu_count}'"
                                        assumptions.append(msg)

                        rpconfig = res_config.get("read_pool_config")
                        if rpconfig:
                            if isinstance(rpconfig, list) and rpconfig:
                                rpconfig_blk = rpconfig[0]
                            else:
                                rpconfig_blk = rpconfig
                            if isinstance(rpconfig_blk, dict):
                                node_count = resolve_value(rpconfig_blk.get("node_count"))
                                if node_count is not None:
                                    attributes["node_count"] = node_count
                                    if _is_unresolved(node_count):
                                        msg = f"Unresolved attribute node_count: '{node_count}'"
                                        assumptions.append(msg)

                        cluster = resolve_value(res_config.get("cluster"))
                        if cluster is not None:
                            attributes["cluster_ref"] = cluster
                            if _is_unresolved(cluster):
                                assumptions.append(f"Unresolved attribute cluster: '{cluster}'")
                    elif res_type_clean == "google_filestore_instance":
                        tier_val = resolve_value(res_config.get("tier"))
                        if tier_val is not None:
                            attributes["tier"] = tier_val

                        file_shares = res_config.get("file_shares", [])
                        if isinstance(file_shares, list) and file_shares:
                            fs = file_shares[0]
                            if isinstance(fs, dict):
                                cap = resolve_value(fs.get("capacity_gb"))
                                if cap is not None:
                                    attributes["capacity_gb"] = cap
                        elif isinstance(file_shares, dict):
                            cap = resolve_value(file_shares.get("capacity_gb"))
                            if cap is not None:
                                attributes["capacity_gb"] = cap

                        if (
                            region
                            and len(region.split("-")) == 3
                            and len(region.split("-")[-1]) == 1
                        ):
                            region = "-".join(region.split("-")[:-1])
                    elif res_type_clean == "google_vertex_ai_endpoint":
                        ded = resolve_value(res_config.get("dedicated_endpoint_enabled"))
                        if ded is not None:
                            attributes["dedicated_endpoint_enabled"] = ded
                    elif res_type_clean == "google_artifact_registry_repository":
                        fmt = resolve_value(res_config.get("format"))
                        if fmt is not None:
                            attributes["format"] = fmt

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

        # Propagate App Engine application location to versions if missing
        app_engine_region = None
        for res in resources:
            if res.kind in ("google_app_engine_application", "app_engine_application"):
                loc = res.attributes.get("location_id") or res.region
                if loc:
                    if loc == "us-central":
                        loc = "us-central1"
                    elif loc == "europe-west":
                        loc = "europe-west1"
                    app_engine_region = loc
                    res.region = loc

        if app_engine_region:
            for res in resources:
                if res.service == "appengine" and not res.region:
                    res.region = app_engine_region

        return ResourceModel(resources=resources)


register_iac_parser("terraform", TerraformHclParser)
