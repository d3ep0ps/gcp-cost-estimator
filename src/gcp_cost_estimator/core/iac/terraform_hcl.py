# SPDX-License-Identifier: Apache-2.0

import re
from pathlib import Path
from typing import Any

import hcl2  # type: ignore[import-untyped]

from gcp_cost_estimator.core.iac.base import IaCParser, register_iac_parser
from gcp_cost_estimator.core.model import Resource, ResourceModel


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
                pass

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

                    if not res_type_clean.startswith("google_"):
                        continue

                    from gcp_cost_estimator.core.iac.gcp import RESOURCE_TYPE_MAP
                    from gcp_cost_estimator.core.iac.gcp.context import ParserContext

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
                        kind = "filestore_instance"
                    elif res_type_clean == "google_vertex_ai_endpoint":
                        service = "vertex_ai"
                        kind = "vertex_ai_endpoint"
                    elif res_type_clean == "google_artifact_registry_repository":
                        service = "artifact_registry"
                        kind = "artifact_registry_repository"
                    else:
                        parts = res_type_clean.split("_")
                        service = parts[1] if len(parts) > 1 else "other"
                        kind = res_type_clean

                        region = ctx.extract_region()
                        quantity = ctx.extract_quantity()

                        attributes = {}
                        for k, v in res_config.items():
                            resolved_v = resolve_value(v)
                            if resolved_v is not None:
                                attributes[k] = resolved_v

                        resources.append(
                            Resource(
                                provider="gcp",
                                resource_id=f"{res_type_clean}.{res_name_clean}",
                                service=service,
                                kind=kind,
                                region=region,
                                attributes=attributes,
                                quantity=quantity,
                                assumptions=ctx.assumptions,
                            )
                        )

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
