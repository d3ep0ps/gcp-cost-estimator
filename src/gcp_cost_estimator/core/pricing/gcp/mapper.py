# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource

# Import service mappers
from gcp_cost_estimator.core.pricing.gcp.alloydb import map_alloydb_cluster, map_alloydb_instance
from gcp_cost_estimator.core.pricing.gcp.appengine import (
    map_app_engine_flexible_version,
    map_app_engine_standard_version,
)
from gcp_cost_estimator.core.pricing.gcp.armor import map_compute_security_policy
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
from gcp_cost_estimator.core.pricing.gcp.vertex_ai import map_vertex_ai_endpoint
from gcp_cost_estimator.core.pricing.gcp.artifact_registry import map_artifact_registry_repository

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
from gcp_cost_estimator.core.pricing.gcp.vpc import map_compute_address
from gcp_cost_estimator.core.registries import SkuMapper, register_sku_mapper


class GcpSkuMapper(SkuMapper):
    """GCP-specific SKU mapper implementing the SkuMapper interface."""

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

    def _map_gce_compute(
        self,
        region: str,
        machine_type: str,
        node_count: int,
        disk_size_gb: float,
        disk_type: str,
        resource_quantity: int,
        resource_id: str,
        cursor: sqlite3.Cursor,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_gce_compute(
            region=region,
            machine_type=machine_type,
            node_count=node_count,
            disk_size_gb=disk_size_gb,
            disk_type=disk_type,
            resource_quantity=resource_quantity,
            resource_id=resource_id,
            cursor=cursor,
        )

    def _map_gke_cluster(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_gke_cluster(resource, cursor)

    def _map_gke_node_pool(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_gke_node_pool(resource, cursor)

    def _map_cloud_sql(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_cloud_sql(resource, cursor)

    def _map_gcs_bucket(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_gcs_bucket(resource, cursor)

    def _map_cloud_cdn_backend(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_cloud_cdn_backend(resource, cursor)

    def _map_dns_managed_zone(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_dns_managed_zone(resource, cursor)

    def _map_nat_gateway(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_nat_gateway(resource, cursor)

    def _map_compute_address(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_compute_address(resource, cursor)

    def _map_compute_security_policy(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_compute_security_policy(resource, cursor)

    def _map_pubsub_topic(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_pubsub_topic(resource, cursor)

    def _map_pubsub_subscription(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_pubsub_subscription(resource, cursor)

    def _map_dataflow_job(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_dataflow_job(resource, cursor)

    def _map_dataproc_cluster(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_dataproc_cluster(resource, cursor)

    def _map_bigquery_dataset(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_bigquery_dataset(resource, cursor)

    def _map_cloud_run_service(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_cloud_run_service(resource, cursor)

    def _map_cloud_run_job(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_cloud_run_job(resource, cursor)

    def _map_cloud_function(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_cloud_function(resource, cursor)

    def _map_app_engine_standard_version(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_app_engine_standard_version(resource, cursor)

    def _map_app_engine_flexible_version(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_app_engine_flexible_version(resource, cursor)

    def _map_spanner_instance(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_spanner_instance(resource, cursor)

    def _map_firestore_database(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_firestore_database(resource, cursor)

    def _map_redis_instance(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_redis_instance(resource, cursor)

    def _map_memorystore_instance(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_memorystore_instance(resource, cursor)

    def _map_bigtable_instance(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_bigtable_instance(resource, cursor)

    def _map_alloydb_cluster(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_alloydb_cluster(resource, cursor)

    def _map_alloydb_instance(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return map_alloydb_instance(resource, cursor)

    def map_resource_to_skus(
        self, resource: Resource
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Decompose a GCP resource (like a VM or PD) into cached billable SKU rates."""
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        if resource.provider != "gcp":
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"GcpSkuMapper cannot process provider '{resource.provider}'",
                }
            )
            return mappings, unpriced

        region = resource.region
        if not region:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "No region specified for GCE resource.",
                }
            )
            return mappings, unpriced

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 1. Compute Instance (GCE VM)
            if resource.service == "compute" and resource.kind == "gce_instance":
                mtype = resource.attributes.get("machine_type", "")
                vm_mappings, vm_unpriced = self._map_gce_compute(
                    region=region,
                    machine_type=mtype,
                    node_count=1,
                    disk_size_gb=0,
                    disk_type="",
                    resource_quantity=resource.quantity,
                    resource_id=resource.resource_id,
                    cursor=cursor,
                )
                mappings.extend(vm_mappings)
                unpriced.extend(vm_unpriced)

                # Process attached resources (like disks)
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

            elif resource.service == "container" and resource.kind == "gke_cluster":
                is_autopilot = resource.attributes.get("enable_autopilot", False)
                if is_autopilot:
                    unpriced.append(
                        {
                            "resource_id": resource.resource_id,
                            "reason": "Autopilot uses per-pod pricing; not yet modelled",
                        }
                    )
                else:
                    gke_mappings, gke_unpriced = self._map_gke_cluster(resource, cursor)
                    mappings.extend(gke_mappings)
                    unpriced.extend(gke_unpriced)

            elif resource.service == "container" and resource.kind == "gke_node_pool":
                pool_mappings, pool_unpriced = self._map_gke_node_pool(resource, cursor)
                mappings.extend(pool_mappings)
                unpriced.extend(pool_unpriced)

            elif resource.service == "sql" and resource.kind == "cloud_sql_instance":
                sql_mappings, sql_unpriced = self._map_cloud_sql(resource, cursor)
                mappings.extend(sql_mappings)
                unpriced.extend(sql_unpriced)
            elif resource.service == "storage" and resource.kind == "gcs_bucket":
                gcs_mappings, gcs_unpriced = self._map_gcs_bucket(resource, cursor)
                mappings.extend(gcs_mappings)
                unpriced.extend(gcs_unpriced)
            elif resource.service == "cdn" and resource.kind == "cloud_cdn_backend":
                cdn_mappings, cdn_unpriced = self._map_cloud_cdn_backend(resource, cursor)
                mappings.extend(cdn_mappings)
                unpriced.extend(cdn_unpriced)
            elif resource.service == "dns" and resource.kind == "dns_managed_zone":
                dns_mappings, dns_unpriced = self._map_dns_managed_zone(resource, cursor)
                mappings.extend(dns_mappings)
                unpriced.extend(dns_unpriced)
            elif resource.service == "nat" and resource.kind == "nat_gateway":
                nat_mappings, nat_unpriced = self._map_nat_gateway(resource, cursor)
                mappings.extend(nat_mappings)
                unpriced.extend(nat_unpriced)
            elif resource.service == "vpc" and resource.kind == "compute_address":
                vpc_mappings, vpc_unpriced = self._map_compute_address(resource, cursor)
                mappings.extend(vpc_mappings)
                unpriced.extend(vpc_unpriced)
            elif resource.service == "armor" and resource.kind == "compute_security_policy":
                armor_mappings, armor_unpriced = self._map_compute_security_policy(resource, cursor)
                mappings.extend(armor_mappings)
                unpriced.extend(armor_unpriced)
            elif resource.service == "pubsub" and resource.kind == "pubsub_topic":
                ps_mappings, ps_unpriced = self._map_pubsub_topic(resource, cursor)
                mappings.extend(ps_mappings)
                unpriced.extend(ps_unpriced)
            elif resource.service == "pubsub" and resource.kind == "pubsub_subscription":
                ps_mappings, ps_unpriced = self._map_pubsub_subscription(resource, cursor)
                mappings.extend(ps_mappings)
                unpriced.extend(ps_unpriced)
            elif resource.service == "dataflow" and resource.kind == "dataflow_job":
                df_mappings, df_unpriced = self._map_dataflow_job(resource, cursor)
                mappings.extend(df_mappings)
                unpriced.extend(df_unpriced)
            elif resource.service == "dataproc" and resource.kind == "dataproc_cluster":
                dp_mappings, dp_unpriced = self._map_dataproc_cluster(resource, cursor)
                mappings.extend(dp_mappings)
                unpriced.extend(dp_unpriced)
            elif resource.service == "bigquery" and resource.kind == "bigquery_dataset":
                bq_mappings, bq_unpriced = self._map_bigquery_dataset(resource, cursor)
                mappings.extend(bq_mappings)
                unpriced.extend(bq_unpriced)
            elif resource.service == "run" and resource.kind == "cloud_run_service":
                run_mappings, run_unpriced = self._map_cloud_run_service(resource, cursor)
                mappings.extend(run_mappings)
                unpriced.extend(run_unpriced)
            elif resource.service == "run" and resource.kind == "cloud_run_job":
                run_mappings, run_unpriced = self._map_cloud_run_job(resource, cursor)
                mappings.extend(run_mappings)
                unpriced.extend(run_unpriced)
            elif resource.service == "functions" and resource.kind == "cloud_function":
                fn_mappings, fn_unpriced = self._map_cloud_function(resource, cursor)
                mappings.extend(fn_mappings)
                unpriced.extend(fn_unpriced)
            elif resource.service == "appengine" and resource.kind == "app_engine_standard_version":
                ae_mappings, ae_unpriced = self._map_app_engine_standard_version(resource, cursor)
                mappings.extend(ae_mappings)
                unpriced.extend(ae_unpriced)
            elif resource.service == "appengine" and resource.kind == "app_engine_flexible_version":
                ae_mappings, ae_unpriced = self._map_app_engine_flexible_version(resource, cursor)
                mappings.extend(ae_mappings)
                unpriced.extend(ae_unpriced)
            elif resource.service == "spanner" and resource.kind == "spanner_instance":
                sp_mappings, sp_unpriced = self._map_spanner_instance(resource, cursor)
                mappings.extend(sp_mappings)
                unpriced.extend(sp_unpriced)
            elif resource.service == "firestore" and resource.kind == "firestore_database":
                fs_mappings, fs_unpriced = self._map_firestore_database(resource, cursor)
                mappings.extend(fs_mappings)
                unpriced.extend(fs_unpriced)
            elif resource.service == "memorystore" and resource.kind == "redis_instance":
                redis_mappings, redis_unpriced = self._map_redis_instance(resource, cursor)
                mappings.extend(redis_mappings)
                unpriced.extend(redis_unpriced)
            elif resource.service == "memorystore" and resource.kind == "memorystore_instance":
                ms_mappings, ms_unpriced = self._map_memorystore_instance(resource, cursor)
                mappings.extend(ms_mappings)
                unpriced.extend(ms_unpriced)
            elif resource.service == "bigtable" and resource.kind == "bigtable_instance":
                bt_mappings, bt_unpriced = self._map_bigtable_instance(resource, cursor)
                mappings.extend(bt_mappings)
                unpriced.extend(bt_unpriced)
            elif resource.service == "alloydb" and resource.kind == "alloydb_cluster":
                ad_mappings, ad_unpriced = self._map_alloydb_cluster(resource, cursor)
                mappings.extend(ad_mappings)
                unpriced.extend(ad_unpriced)
            elif resource.service == "alloydb" and resource.kind == "alloydb_instance":
                adi_mappings, adi_unpriced = self._map_alloydb_instance(resource, cursor)
                mappings.extend(adi_mappings)
                unpriced.extend(adi_unpriced)
            elif resource.kind == "google_filestore_instance":
                fs_mappings, fs_unpriced = map_filestore_instance(resource, cursor)
                mappings.extend(fs_mappings)
                unpriced.extend(fs_unpriced)
            elif resource.kind == "google_vertex_ai_endpoint":
                vai_mappings, vai_unpriced = map_vertex_ai_endpoint(resource, cursor)
                mappings.extend(vai_mappings)
                unpriced.extend(vai_unpriced)
            elif resource.kind == "google_artifact_registry_repository":
                ar_mappings, ar_unpriced = map_artifact_registry_repository(resource, cursor)
                mappings.extend(ar_mappings)
                unpriced.extend(ar_unpriced)
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"Unsupported resource kind '{resource.kind}'",
                    }
                )
        finally:
            conn.close()

        return mappings, unpriced


# Register the SKU mapper in global registry
register_sku_mapper("gcp", GcpSkuMapper)
