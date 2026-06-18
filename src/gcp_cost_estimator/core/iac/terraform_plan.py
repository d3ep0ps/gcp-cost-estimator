# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any

from gcp_cost_estimator.core.iac.base import IaCParser, get_iac_parser, register_iac_parser
from gcp_cost_estimator.core.model import Resource, ResourceModel


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

            address = raw_res.get("address", "")
            values = raw_res.get("values", {})

            from gcp_cost_estimator.core.iac.gcp import RESOURCE_TYPE_MAP
            from gcp_cost_estimator.core.iac.gcp.context import ParserContext

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
                kind = "filestore_instance"
            elif res_type == "google_vertex_ai_endpoint":
                service = "vertex_ai"
                kind = "vertex_ai_endpoint"
            elif res_type == "google_artifact_registry_repository":
                service = "artifact_registry"
                kind = "artifact_registry_repository"
            else:
                parts = res_type.split("_")
                service = parts[1] if len(parts) > 1 else "other"
                kind = res_type

                region = ctx.extract_region()
                quantity = 1

                attributes = {}
                for k, v in values.items():
                    if v is not None:
                        attributes[k] = v

                resources.append(
                    Resource(
                        provider="gcp",
                        resource_id=address,
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
