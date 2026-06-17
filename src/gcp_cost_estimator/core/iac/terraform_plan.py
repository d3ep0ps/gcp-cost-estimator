# SPDX-License-Identifier: Apache-2.0

import contextlib
import json
import re
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
            elif res_type == "google_cloud_run_v2_service":
                service = "run"
                kind = "cloud_run_service"
            elif res_type == "google_cloud_run_v2_job":
                service = "run"
                kind = "cloud_run_job"
            elif res_type in (
                "google_cloudfunctions_function",
                "google_cloudfunctions2_function",
            ):
                service = "functions"
                kind = "cloud_function"
            elif res_type == "google_app_engine_standard_app_version":
                service = "appengine"
                kind = "app_engine_standard_version"
            elif res_type == "google_app_engine_flexible_app_version":
                service = "appengine"
                kind = "app_engine_flexible_version"
            elif res_type == "google_spanner_instance":
                service = "spanner"
                kind = "spanner_instance"
            elif res_type == "google_firestore_database":
                service = "firestore"
                kind = "firestore_database"
            elif res_type == "google_redis_instance":
                service = "memorystore"
                kind = "redis_instance"
            elif res_type == "google_memorystore_instance":
                service = "memorystore"
                kind = "memorystore_instance"
            elif res_type == "google_bigtable_instance":
                service = "bigtable"
                kind = "bigtable_instance"
            elif res_type == "google_alloydb_cluster":
                service = "alloydb"
                kind = "alloydb_cluster"
            elif res_type == "google_alloydb_instance":
                service = "alloydb"
                kind = "alloydb_instance"
            elif res_type in (
                "google_compute_backend_bucket",
                "google_compute_backend_service",
            ) and values.get("cdn_policy"):
                service = "cdn"
                kind = "cloud_cdn_backend"
            elif res_type == "google_app_engine_application":
                service = "appengine"
                kind = "google_app_engine_application"
            elif res_type == "google_dns_managed_zone":
                service = "dns"
                kind = "dns_managed_zone"
            elif res_type == "google_compute_router_nat":
                service = "nat"
                kind = "nat_gateway"
            elif res_type == "google_compute_address":
                service = "vpc"
                kind = "compute_address"
            elif res_type == "google_compute_security_policy":
                service = "armor"
                kind = "compute_security_policy"
            elif res_type == "google_pubsub_topic":
                service = "pubsub"
                kind = "pubsub_topic"
            elif res_type == "google_pubsub_subscription":
                service = "pubsub"
                kind = "pubsub_subscription"
            elif res_type == "google_pubsub_lite_topic":
                service = "pubsub"
                kind = "pubsub_lite_topic"
            elif res_type == "google_pubsub_lite_subscription":
                service = "pubsub"
                kind = "pubsub_lite_subscription"
            elif res_type == "google_dataflow_job":
                service = "dataflow"
                kind = "dataflow_job"
            elif res_type == "google_dataproc_cluster":
                service = "dataproc"
                kind = "dataproc_cluster"
            elif res_type == "google_dataproc_serverless_batch":
                service = "dataproc"
                kind = "dataproc_serverless_batch"
            elif res_type == "google_filestore_instance":
                service = "filestore"
                kind = "google_filestore_instance"
            elif res_type == "google_vertex_ai_endpoint":
                service = "vertex"
                kind = "google_vertex_ai_endpoint"
            elif res_type == "google_artifact_registry_repository":
                service = "artifact"
                kind = "google_artifact_registry_repository"
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

            if kind in (
                "dns_managed_zone",
                "compute_security_policy",
                "pubsub_topic",
                "pubsub_subscription",
            ):
                region = "global"

            attributes: dict[str, Any] = {}
            attached: list[AttachedResource] = []

            if kind == "cloud_cdn_backend":
                attributes["cdn_enabled"] = True

            if kind == "dns_managed_zone":
                visibility = values.get("visibility")
                if visibility:
                    attributes["visibility"] = visibility
                else:
                    attributes["visibility"] = "public"

            if kind == "nat_gateway":
                allocate_option = values.get("nat_ip_allocate_option")
                if allocate_option:
                    attributes["nat_ip_allocate_option"] = allocate_option

            if kind == "compute_address":
                addr_type = values.get("address_type")
                if addr_type:
                    attributes["address_type"] = addr_type
                purpose = values.get("purpose")
                if purpose:
                    attributes["purpose"] = purpose

            if kind == "compute_security_policy":
                rules = values.get("rule", [])
                if isinstance(rules, dict):
                    attributes["rule_count"] = 1
                elif isinstance(rules, list):
                    attributes["rule_count"] = len(rules)
                else:
                    attributes["rule_count"] = 0

            if kind == "pubsub_subscription":
                retain = values.get("retain_acked_messages")
                if retain is not None:
                    attributes["retain_acked_messages"] = retain

            if kind == "dataflow_job":
                mtype = values.get("machine_type")
                if mtype:
                    attributes["machine_type"] = mtype
                max_w = values.get("max_workers")
                if max_w is not None:
                    attributes["max_workers"] = max_w

            if kind == "dataproc_cluster":
                master_configs = values.get("master_config", [])
                if isinstance(master_configs, dict):
                    master_configs = [master_configs]
                if isinstance(master_configs, list) and master_configs:
                    mc = master_configs[0]
                    if isinstance(mc, dict):
                        num_inst = mc.get("num_instances")
                        m_type = mc.get("machine_type")
                        if num_inst is not None:
                            attributes["num_master_nodes"] = num_inst
                        if m_type is not None:
                            attributes["master_machine_type"] = m_type

                worker_configs = values.get("worker_config", [])
                if isinstance(worker_configs, dict):
                    worker_configs = [worker_configs]
                if isinstance(worker_configs, list) and worker_configs:
                    wc = worker_configs[0]
                    if isinstance(wc, dict):
                        num_inst = wc.get("num_instances")
                        w_type = wc.get("machine_type")
                        if num_inst is not None:
                            attributes["num_worker_nodes"] = num_inst
                        if w_type is not None:
                            attributes["worker_machine_type"] = w_type

                preempt_configs = values.get("preemptible_worker_config", [])
                if isinstance(preempt_configs, dict):
                    preempt_configs = [preempt_configs]
                if isinstance(preempt_configs, list) and preempt_configs:
                    pc = preempt_configs[0]
                    if isinstance(pc, dict):
                        num_inst = pc.get("num_instances")
                        if num_inst is not None:
                            attributes["num_preemptible_nodes"] = num_inst

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
            elif res_type == "google_cloud_run_v2_service":
                template_list = values.get("template", [])
                if isinstance(template_list, list) and template_list:
                    template = template_list[0]
                    if isinstance(template, dict):
                        scaling_list = template.get("scaling", [])
                        if isinstance(scaling_list, list) and scaling_list:
                            scaling = scaling_list[0]
                            if isinstance(scaling, dict):
                                for field in ("min_instance_count", "max_instance_count"):
                                    val = scaling.get(field)
                                    if val is not None:
                                        with contextlib.suppress(ValueError, TypeError):
                                            attributes[field] = int(val)
                        containers = template.get("containers", [])
                        if isinstance(containers, list) and containers:
                            container = containers[0]
                            if isinstance(container, dict):
                                resources_list = container.get("resources", [])
                                if isinstance(resources_list, list) and resources_list:
                                    res_conf = resources_list[0]
                                    if isinstance(res_conf, dict):
                                        cpu_idle_val = res_conf.get("cpu_idle")
                                        if cpu_idle_val is not None:
                                            attributes["cpu_idle"] = bool(cpu_idle_val)
                                        limits = res_conf.get("limits")
                                        if isinstance(limits, dict):
                                            for limit_key in ("cpu", "memory"):
                                                val = limits.get(limit_key)
                                                if val is not None:
                                                    attributes[limit_key] = val

            elif res_type == "google_cloud_run_v2_job":
                template_list = values.get("template", [])
                if isinstance(template_list, list) and template_list:
                    template = template_list[0]
                    if isinstance(template, dict):
                        sub_template_list = template.get("template", [])
                        if isinstance(sub_template_list, list) and sub_template_list:
                            sub_template = sub_template_list[0]
                            if isinstance(sub_template, dict):
                                containers = sub_template.get("containers", [])
                                if isinstance(containers, list) and containers:
                                    container = containers[0]
                                    if isinstance(container, dict):
                                        resources_list = container.get("resources", [])
                                        if isinstance(resources_list, list) and resources_list:
                                            res_conf = resources_list[0]
                                            if isinstance(res_conf, dict):
                                                limits = res_conf.get("limits")
                                                if isinstance(limits, dict):
                                                    for limit_key in ("cpu", "memory"):
                                                        val = limits.get(limit_key)
                                                        if val is not None:
                                                            attributes[limit_key] = val
            elif res_type == "google_cloudfunctions_function":
                attributes["generation"] = "1st_gen"
                for field in ("available_memory_mb", "min_instances"):
                    val = values.get(field)
                    if val is not None:
                        attributes[field] = val

            elif res_type == "google_cloudfunctions2_function":
                attributes["generation"] = "2nd_gen"
                sc_list = values.get("service_config", [])
                if isinstance(sc_list, list) and sc_list:
                    sc = sc_list[0]
                    if isinstance(sc, dict):
                        for field in (
                            "available_memory",
                            "available_cpu",
                            "min_instance_count",
                            "max_instance_count",
                        ):
                            val = sc.get(field)
                            if val is not None:
                                attributes[field] = val

            elif res_type == "google_app_engine_standard_app_version":
                iclass = values.get("instance_class")
                if iclass:
                    attributes["instance_class"] = iclass

                for scaling_type in ("automatic_scaling", "basic_scaling", "manual_scaling"):
                    scaling_list = values.get(scaling_type, [])
                    if isinstance(scaling_list, list) and scaling_list:
                        attributes["scaling_type"] = scaling_type
                        scaling_blk = scaling_list[0]
                        if isinstance(scaling_blk, dict):
                            for k, v in scaling_blk.items():
                                attributes[f"{scaling_type}_{k}"] = v

            elif res_type == "google_app_engine_flexible_app_version":
                resources_blk = values.get("resources")
                if isinstance(resources_blk, list) and resources_blk:
                    resources_blk = resources_blk[0]
                if isinstance(resources_blk, dict):
                    for field in ("cpu", "memory_gb", "disk_gb"):
                        val = resources_blk.get(field)
                        if val is not None:
                            attributes[field] = val
                else:
                    assumptions.append("No resources configuration found; using defaults.")

            elif res_type == "google_spanner_instance":
                for field in ("config", "num_nodes", "processing_units", "edition"):
                    val = values.get(field)
                    if val is not None:
                        attributes[field] = val
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

            elif res_type == "google_firestore_database":
                db_type = values.get("type")
                if db_type is not None:
                    attributes["database_type"] = db_type
                loc_id = values.get("location_id")
                if loc_id is not None:
                    region = loc_id

            elif res_type == "google_redis_instance":
                for field in ("memory_size_gb", "tier", "region", "redis_version"):
                    val = values.get(field)
                    if val is not None:
                        attributes[field] = val
                if not region and attributes.get("region"):
                    region = attributes["region"]

            elif res_type == "google_memorystore_instance":
                for field in ("instance_id", "location", "shard_count", "node_type", "mode"):
                    val = values.get(field)
                    if val is not None:
                        attributes[field] = val
                if not region and attributes.get("location"):
                    region = attributes["location"]

            elif res_type == "google_bigtable_instance":
                inst_type = values.get("instance_type")
                if inst_type is not None:
                    attributes["instance_type"] = inst_type

                clusters_raw = values.get("cluster")
                if clusters_raw:
                    if not isinstance(clusters_raw, list):
                        clusters_raw = [clusters_raw]
                    clusters_list = []
                    for cl in clusters_raw:
                        if isinstance(cl, dict):
                            cl_dict = {}
                            for k, v in cl.items():
                                if v is not None:
                                    cl_dict[k] = v
                            clusters_list.append(cl_dict)
                    attributes["clusters"] = clusters_list

                if clusters_raw and not region:
                    first_cl = clusters_raw[0]
                    if isinstance(first_cl, dict):
                        first_zone = first_cl.get("zone")
                        if first_zone:
                            region = re.sub(r"-[a-z]$", "", str(first_zone).strip()).lower()

            elif res_type == "google_alloydb_cluster":
                initial_user = values.get("initial_user")
                if initial_user:
                    if isinstance(initial_user, list) and initial_user:
                        initial_user_blk = initial_user[0]
                    else:
                        initial_user_blk = initial_user
                    if isinstance(initial_user_blk, dict):
                        initial_user_blk_copy = dict(initial_user_blk)
                        initial_user_blk_copy.pop("password", None)
                        attributes["initial_user"] = initial_user_blk_copy

                for k, v in values.items():
                    if k == "initial_user":
                        continue
                    if v is not None:
                        attributes[k] = v
                if not region and attributes.get("location"):
                    region = attributes["location"]

            elif res_type == "google_alloydb_instance":
                itype = values.get("instance_type")
                if itype is not None:
                    attributes["instance_type"] = itype

                mconfig = values.get("machine_config")
                if mconfig:
                    mconfig_blk = mconfig[0] if isinstance(mconfig, list) and mconfig else mconfig
                    if isinstance(mconfig_blk, dict):
                        cpu_count = mconfig_blk.get("cpu_count")
                        if cpu_count is not None:
                            attributes["cpu_count"] = cpu_count

                rpconfig = values.get("read_pool_config")
                if rpconfig:
                    rpconfig_blk = (
                        rpconfig[0] if isinstance(rpconfig, list) and rpconfig else rpconfig
                    )
                    if isinstance(rpconfig_blk, dict):
                        node_count = rpconfig_blk.get("node_count")
                        if node_count is not None:
                            attributes["node_count"] = node_count

                cluster = values.get("cluster")
                if cluster is not None:
                    if isinstance(cluster, str) and "/clusters/" in cluster:
                        cluster_id = cluster.split("/clusters/")[-1]
                        attributes["cluster_ref"] = cluster_id
                        if "/locations/" in cluster:
                            loc_part = cluster.split("/locations/")[1].split("/")[0]
                            region = loc_part
                    else:
                        attributes["cluster_ref"] = cluster
            elif res_type == "google_filestore_instance":
                tier_val = values.get("tier")
                if tier_val is not None:
                    attributes["tier"] = tier_val
                
                file_shares = values.get("file_shares", [])
                if isinstance(file_shares, list) and file_shares:
                    fs = file_shares[0]
                    if isinstance(fs, dict):
                        cap = fs.get("capacity_gb")
                        if cap is not None:
                            attributes["capacity_gb"] = cap
                elif isinstance(file_shares, dict):
                    cap = file_shares.get("capacity_gb")
                    if cap is not None:
                        attributes["capacity_gb"] = cap

                if region and len(region.split("-")) == 3 and len(region.split("-")[-1]) == 1:
                    region = "-".join(region.split("-")[:-1])
            elif res_type == "google_vertex_ai_endpoint":
                ded = values.get("dedicated_endpoint_enabled")
                if ded is not None:
                    attributes["dedicated_endpoint_enabled"] = ded
            elif res_type == "google_artifact_registry_repository":
                fmt = values.get("format")
                if fmt is not None:
                    attributes["format"] = fmt

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
