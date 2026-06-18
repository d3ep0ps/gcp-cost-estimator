# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable

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
}
