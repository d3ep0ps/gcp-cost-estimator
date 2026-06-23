# SPDX-License-Identifier: Apache-2.0

import sqlite3
from collections.abc import Callable
from typing import Any, ClassVar

from gcp_cost_estimator.core.model import Resource

# Import service mappers
from gcp_cost_estimator.core.pricing.gcp.alloydb import map_alloydb_cluster, map_alloydb_instance
from gcp_cost_estimator.core.pricing.gcp.appengine import (
    map_app_engine_flexible_version,
    map_app_engine_standard_version,
)
from gcp_cost_estimator.core.pricing.gcp.armor import map_compute_security_policy
from gcp_cost_estimator.core.pricing.gcp.artifact_registry import map_artifact_registry_repository
from gcp_cost_estimator.core.pricing.gcp.bigquery import map_bigquery_dataset
from gcp_cost_estimator.core.pricing.gcp.bigtable import map_bigtable_instance
from gcp_cost_estimator.core.pricing.gcp.cdn import map_cloud_cdn_backend
from gcp_cost_estimator.core.pricing.gcp.compute import (
    map_gce_compute,
    map_gke_cluster,
    map_gke_node_pool,
)
from gcp_cost_estimator.core.pricing.gcp.dataflow import map_dataflow_job
from gcp_cost_estimator.core.pricing.gcp.dataproc import map_dataproc_cluster
from gcp_cost_estimator.core.pricing.gcp.dns import map_dns_managed_zone
from gcp_cost_estimator.core.pricing.gcp.filestore import map_filestore_instance
from gcp_cost_estimator.core.pricing.gcp.firestore import map_firestore_database
from gcp_cost_estimator.core.pricing.gcp.memorystore import (
    map_memorystore_instance,
    map_redis_instance,
)
from gcp_cost_estimator.core.pricing.gcp.nat import map_nat_gateway
from gcp_cost_estimator.core.pricing.gcp.pubsub import map_pubsub_subscription, map_pubsub_topic
from gcp_cost_estimator.core.pricing.gcp.serverless import (
    map_cloud_function,
    map_cloud_run_job,
    map_cloud_run_service,
)
from gcp_cost_estimator.core.pricing.gcp.spanner import map_spanner_instance
from gcp_cost_estimator.core.pricing.gcp.sql import map_cloud_sql
from gcp_cost_estimator.core.pricing.gcp.storage import map_gcs_bucket
from gcp_cost_estimator.core.pricing.gcp.vertex_ai import map_vertex_ai_endpoint
from gcp_cost_estimator.core.pricing.gcp.vpc import map_compute_address
from gcp_cost_estimator.core.registries import SkuMapper, register_sku_mapper

# Type alias for mapper functions
_MapperFn = Callable[[Resource, sqlite3.Cursor], tuple[list[dict[str, Any]], list[dict[str, Any]]]]


def _map_gce_instance_with_attached(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Handle GCE instance mapping including any attached disk resources."""
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []
    region = resource.region or ""

    vm_mappings, vm_unpriced = map_gce_compute(
        region=region,
        machine_type=resource.attributes.get("machine_type", ""),
        node_count=1,
        disk_size_gb=0,
        disk_type="",
        resource_quantity=resource.quantity,
        resource_id=resource.resource_id,
        cursor=cursor,
    )
    mappings.extend(vm_mappings)
    unpriced.extend(vm_unpriced)

    for attached in resource.attached:
        if "disk" in attached.kind.lower():
            sku_group = "SSD" if "ssd" in attached.kind.lower() else "PDStandard"
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = ?
                """,
                (region, sku_group),
            )
            disk_rows = cursor.fetchall()
            if disk_rows:
                disk_match = disk_rows[0]
                size_gb = float(attached.attributes.get("size_gb", 0))
                mappings.append(
                    {
                        "sku_id": disk_match[0],
                        "component": "storage",
                        "unit": disk_match[1],
                        "unit_price": disk_match[2],
                        "qty": size_gb * attached.quantity * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": f"{resource.resource_id}/{attached.kind}",
                        "reason": (
                            f"No matching storage SKU found for '{attached.kind}' "
                            f"in region {region}"
                        ),
                    }
                )
        else:
            unpriced.append(
                {
                    "resource_id": f"{resource.resource_id}/{attached.kind}",
                    "reason": f"Unsupported attached resource kind '{attached.kind}'",
                }
            )

    return mappings, unpriced


def _map_gke_cluster_with_autopilot(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Handle GKE cluster mapping, surfacing Autopilot as unpriced."""
    if resource.attributes.get("enable_autopilot", False):
        return [], [
            {
                "resource_id": resource.resource_id,
                "reason": "Autopilot uses per-pod pricing; not yet modelled",
            }
        ]
    return map_gke_cluster(resource, cursor)


class GcpSkuMapper(SkuMapper):
    """GCP-specific SKU mapper implementing the SkuMapper interface."""

    # Dispatch table: (service, kind) -> mapping function.
    # To add a new GCP resource: import its mapper and add one entry here.
    _DISPATCH: ClassVar[dict[tuple[str, str], _MapperFn]] = {
        ("compute", "gce_instance"): _map_gce_instance_with_attached,
        ("container", "gke_cluster"): _map_gke_cluster_with_autopilot,
        ("container", "gke_node_pool"): map_gke_node_pool,
        ("sql", "cloud_sql_instance"): map_cloud_sql,
        ("storage", "gcs_bucket"): map_gcs_bucket,
        ("cdn", "cloud_cdn_backend"): map_cloud_cdn_backend,
        ("dns", "dns_managed_zone"): map_dns_managed_zone,
        ("nat", "nat_gateway"): map_nat_gateway,
        ("vpc", "compute_address"): map_compute_address,
        ("armor", "compute_security_policy"): map_compute_security_policy,
        ("pubsub", "pubsub_topic"): map_pubsub_topic,
        ("pubsub", "pubsub_subscription"): map_pubsub_subscription,
        ("dataflow", "dataflow_job"): map_dataflow_job,
        ("dataproc", "dataproc_cluster"): map_dataproc_cluster,
        ("bigquery", "bigquery_dataset"): map_bigquery_dataset,
        ("run", "cloud_run_service"): map_cloud_run_service,
        ("run", "cloud_run_job"): map_cloud_run_job,
        ("functions", "cloud_function"): map_cloud_function,
        ("appengine", "app_engine_standard_version"): map_app_engine_standard_version,
        ("appengine", "app_engine_flexible_version"): map_app_engine_flexible_version,
        ("spanner", "spanner_instance"): map_spanner_instance,
        ("firestore", "firestore_database"): map_firestore_database,
        ("memorystore", "redis_instance"): map_redis_instance,
        ("memorystore", "memorystore_instance"): map_memorystore_instance,
        ("bigtable", "bigtable_instance"): map_bigtable_instance,
        ("alloydb", "alloydb_cluster"): map_alloydb_cluster,
        ("alloydb", "alloydb_instance"): map_alloydb_instance,
        ("filestore", "filestore_instance"): map_filestore_instance,
        ("vertex_ai", "vertex_ai_endpoint"): map_vertex_ai_endpoint,
        ("artifact_registry", "artifact_registry_repository"): map_artifact_registry_repository,
    }

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._conn: sqlite3.Connection | None = None

    def _get_cursor(self) -> sqlite3.Cursor:
        """Return a cursor, opening the shared connection on first call."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._conn.cursor()

    def close(self) -> None:
        """Close the shared SQLite connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def get_supported_billing_services(cls) -> list[str]:
        """Return the list of official billing service display names required by this provider."""
        return [
            "Compute Engine",
            "Cloud CDN",
            "Cloud DNS",
            "Cloud NAT",
            "Cloud Armor",
            "Pub/Sub",
            "Dataflow",
            "Dataproc",
            "Cloud SQL",
            "Cloud Storage",
            "Kubernetes Engine",
            "BigQuery",
            "Cloud Run",
            "Cloud Functions",
            "App Engine",
            "Spanner",
            "Cloud Spanner",
            "Firestore",
            "Cloud Firestore",
            "Bigtable",
            "Cloud Bigtable",
            "AlloyDB",
            "AlloyDB for PostgreSQL",
            "Memorystore for Redis",
            "Memorystore for Valkey",
            "Memorystore",
            "Filestore",
            "Vertex AI",
            "Artifact Registry",
        ]

    def map_resource_to_skus(
        self, resource: Resource
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Decompose a GCP resource into cached billable SKU rates via the dispatch table."""
        if resource.provider != "gcp":
            return [], [
                {
                    "resource_id": resource.resource_id,
                    "reason": f"GcpSkuMapper cannot process provider '{resource.provider}'",
                }
            ]

        if not resource.region:
            return [], [
                {
                    "resource_id": resource.resource_id,
                    "reason": "No region specified for GCE resource.",
                }
            ]

        fn = self._DISPATCH.get((resource.service, resource.kind))
        if fn is None:
            return [], [
                {
                    "resource_id": resource.resource_id,
                    "reason": f"Unsupported resource kind '{resource.kind}'",
                }
            ]

        return fn(resource, self._get_cursor())


# Register the SKU mapper in global registry
register_sku_mapper("gcp", GcpSkuMapper)
