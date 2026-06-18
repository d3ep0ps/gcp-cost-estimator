# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable

from gcp_cost_estimator.core.iac.gcp.compute import (
    parse_compute_disk,
    parse_compute_instance,
)
from gcp_cost_estimator.core.iac.gcp.container import (
    parse_container_cluster,
    parse_container_node_pool,
)
from gcp_cost_estimator.core.iac.gcp.context import ParserContext
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
}
