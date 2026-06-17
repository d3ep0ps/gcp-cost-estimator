# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.validation.gcp.alloydb import normalize_alloydb, validate_alloydb
from gcp_cost_estimator.core.validation.gcp.appengine import normalize_appengine, validate_appengine
from gcp_cost_estimator.core.validation.gcp.armor import normalize_armor, validate_armor
from gcp_cost_estimator.core.validation.gcp.artifact_registry import (
    normalize_artifact_registry,
    validate_artifact_registry,
)
from gcp_cost_estimator.core.validation.gcp.bigquery import normalize_bigquery, validate_bigquery
from gcp_cost_estimator.core.validation.gcp.bigtable import normalize_bigtable, validate_bigtable
from gcp_cost_estimator.core.validation.gcp.cdn import normalize_cdn, validate_cdn
from gcp_cost_estimator.core.validation.gcp.compute import normalize_compute, validate_compute
from gcp_cost_estimator.core.validation.gcp.container import normalize_container, validate_container
from gcp_cost_estimator.core.validation.gcp.dataflow import normalize_dataflow, validate_dataflow
from gcp_cost_estimator.core.validation.gcp.dataproc import normalize_dataproc, validate_dataproc
from gcp_cost_estimator.core.validation.gcp.dns import normalize_dns, validate_dns
from gcp_cost_estimator.core.validation.gcp.filestore import (
    normalize_filestore,
    validate_filestore,
)
from gcp_cost_estimator.core.validation.gcp.firestore import normalize_firestore, validate_firestore
from gcp_cost_estimator.core.validation.gcp.functions import normalize_functions, validate_functions
from gcp_cost_estimator.core.validation.gcp.memorystore import (
    normalize_memorystore,
    validate_memorystore,
)
from gcp_cost_estimator.core.validation.gcp.nat import normalize_nat, validate_nat
from gcp_cost_estimator.core.validation.gcp.pubsub import normalize_pubsub, validate_pubsub
from gcp_cost_estimator.core.validation.gcp.run import normalize_run, validate_run
from gcp_cost_estimator.core.validation.gcp.spanner import normalize_spanner, validate_spanner
from gcp_cost_estimator.core.validation.gcp.sql import normalize_sql, validate_sql
from gcp_cost_estimator.core.validation.gcp.storage import normalize_storage, validate_storage
from gcp_cost_estimator.core.validation.gcp.vertex_ai import (
    normalize_vertex_ai_endpoint,
    validate_vertex_ai_endpoint,
)
from gcp_cost_estimator.core.validation.gcp.vpc import normalize_vpc, validate_vpc

VALIDATORS = {
    "storage": validate_storage,
    "compute": validate_compute,
    "sql": validate_sql,
    "container": validate_container,
    "run": validate_run,
    "functions": validate_functions,
    "appengine": validate_appengine,
    "bigquery": validate_bigquery,
    "spanner": validate_spanner,
    "firestore": validate_firestore,
    "memorystore": validate_memorystore,
    "bigtable": validate_bigtable,
    "alloydb": validate_alloydb,
    "cdn": validate_cdn,
    "dataflow": validate_dataflow,
    "dataproc": validate_dataproc,
    "dns": validate_dns,
    "nat": validate_nat,
    "vpc": validate_vpc,
    "armor": validate_armor,
    "pubsub": validate_pubsub,
    "filestore": validate_filestore,
    "vertex": validate_vertex_ai_endpoint,
    "artifact": validate_artifact_registry,
}

NORMALIZERS = {
    "storage": normalize_storage,
    "compute": normalize_compute,
    "sql": normalize_sql,
    "container": normalize_container,
    "run": normalize_run,
    "functions": normalize_functions,
    "appengine": normalize_appengine,
    "bigquery": normalize_bigquery,
    "spanner": normalize_spanner,
    "firestore": normalize_firestore,
    "memorystore": normalize_memorystore,
    "bigtable": normalize_bigtable,
    "alloydb": normalize_alloydb,
    "cdn": normalize_cdn,
    "dataflow": normalize_dataflow,
    "dataproc": normalize_dataproc,
    "dns": normalize_dns,
    "nat": normalize_nat,
    "vpc": normalize_vpc,
    "armor": normalize_armor,
    "pubsub": normalize_pubsub,
    "filestore": normalize_filestore,
    "vertex": normalize_vertex_ai_endpoint,
    "artifact": normalize_artifact_registry,
}
