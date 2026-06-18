# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable

from gcp_cost_estimator.core.iac.gcp.analytics import (
    parse_dataflow_job,
    parse_dataproc_cluster,
    parse_dataproc_serverless_batch,
    parse_pubsub_lite_subscription,
    parse_pubsub_lite_topic,
    parse_pubsub_subscription,
    parse_pubsub_topic,
)
from gcp_cost_estimator.core.iac.gcp.bigquery import parse_bigquery_dataset
from gcp_cost_estimator.core.iac.gcp.compute import (
    parse_compute_disk,
    parse_compute_instance,
)
from gcp_cost_estimator.core.iac.gcp.container import (
    parse_container_cluster,
    parse_container_node_pool,
)
from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.iac.gcp.databases import (
    parse_alloydb_cluster,
    parse_alloydb_instance,
    parse_bigtable_instance,
    parse_firestore_database,
    parse_memorystore_instance,
    parse_redis_instance,
    parse_spanner_instance,
)
from gcp_cost_estimator.core.iac.gcp.networking import (
    parse_compute_address,
    parse_compute_backend,
    parse_compute_security_policy,
    parse_dns_managed_zone,
    parse_nat_gateway,
)
from gcp_cost_estimator.core.iac.gcp.serverless import (
    parse_app_engine_application,
    parse_app_engine_flexible_version,
    parse_app_engine_standard_version,
    parse_cloud_run_job,
    parse_cloud_run_service,
    parse_cloudfunctions2_function,
    parse_cloudfunctions_function,
)
from gcp_cost_estimator.core.iac.gcp.sql import parse_sql_database_instance
from gcp_cost_estimator.core.iac.gcp.storage import parse_storage_bucket
from gcp_cost_estimator.core.model import Resource

ParserFunc = Callable[[str, ParserContext, dict[str, str]], Resource]

RESOURCE_TYPE_MAP: dict[str, ParserFunc] = {
    "google_compute_instance": parse_compute_instance,
    "google_compute_disk": parse_compute_disk,
    "google_sql_database_instance": parse_sql_database_instance,
    "google_storage_bucket": parse_storage_bucket,
    "google_container_cluster": parse_container_cluster,
    "google_container_node_pool": parse_container_node_pool,
    "google_bigquery_dataset": parse_bigquery_dataset,
    "google_cloud_run_v2_service": parse_cloud_run_service,
    "google_cloud_run_v2_job": parse_cloud_run_job,
    "google_cloudfunctions_function": parse_cloudfunctions_function,
    "google_cloudfunctions2_function": parse_cloudfunctions2_function,
    "google_app_engine_standard_app_version": parse_app_engine_standard_version,
    "google_app_engine_flexible_app_version": parse_app_engine_flexible_version,
    "google_app_engine_application": parse_app_engine_application,
    "google_spanner_instance": parse_spanner_instance,
    "google_firestore_database": parse_firestore_database,
    "google_redis_instance": parse_redis_instance,
    "google_memorystore_instance": parse_memorystore_instance,
    "google_bigtable_instance": parse_bigtable_instance,
    "google_alloydb_cluster": parse_alloydb_cluster,
    "google_alloydb_instance": parse_alloydb_instance,
    "google_dns_managed_zone": parse_dns_managed_zone,
    "google_compute_router_nat": parse_nat_gateway,
    "google_compute_address": parse_compute_address,
    "google_compute_security_policy": parse_compute_security_policy,
    "google_compute_backend_bucket": parse_compute_backend,
    "google_compute_backend_service": parse_compute_backend,
    "google_pubsub_topic": parse_pubsub_topic,
    "google_pubsub_subscription": parse_pubsub_subscription,
    "google_pubsub_lite_topic": parse_pubsub_lite_topic,
    "google_pubsub_lite_subscription": parse_pubsub_lite_subscription,
    "google_dataflow_job": parse_dataflow_job,
    "google_dataproc_cluster": parse_dataproc_cluster,
    "google_dataproc_serverless_batch": parse_dataproc_serverless_batch,
}
