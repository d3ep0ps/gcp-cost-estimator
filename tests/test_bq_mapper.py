# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_bq_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static BigQuery SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/bq_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_bigquery_active_storage_maps_to_active_storage_sku(populated_bq_db: str) -> None:
    """Verify active storage maps to active storage SKU in regional/multi-regional locations."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"active_storage_gb": 120.0},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "active_storage")
    assert storage_map["sku_id"] == "BQ-ACTIVE-STORAGE-US"
    assert storage_map["qty"] == 120.0


def test_bigquery_long_term_storage_maps_to_long_term_sku(populated_bq_db: str) -> None:
    """Verify long-term storage mapping."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"long_term_storage_gb": 80.0},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "long_term_storage")
    assert storage_map["sku_id"] == "BQ-LONG-TERM-STORAGE-US"
    assert storage_map["qty"] == 80.0


def test_bigquery_query_tb_maps_to_on_demand_query_sku(populated_bq_db: str) -> None:
    """Verify query mapping."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"monthly_query_tb": 2.5},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    query_map = next(m for m in mappings if m["component"] == "query_scan")
    assert query_map["sku_id"] == "BQ-ANALYSIS-US"
    assert query_map["qty"] == 2.5


def test_bigquery_streaming_maps_to_streaming_sku(populated_bq_db: str) -> None:
    """Verify streaming mapping."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"monthly_streaming_gb": 50.0},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    streaming_map = next(m for m in mappings if m["component"] == "streaming_insert")
    assert streaming_map["sku_id"] == "BQ-STREAMING-US"
    assert streaming_map["qty"] == 50.0


def test_bigquery_zero_usage_fields_emit_no_skus(populated_bq_db: str) -> None:
    """Verify zero usage fields emit no SKUs to avoid noise."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={
            "active_storage_gb": 0.0,
            "long_term_storage_gb": 0.0,
            "monthly_query_tb": 0.0,
            "monthly_streaming_gb": 0.0,
        },
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 0


def test_bigquery_region_specific_sku_selected(populated_bq_db: str) -> None:
    """Verify regional selection (e.g. us-central1)."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us-central1",
        usage={"active_storage_gb": 100.0},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "active_storage")
    assert storage_map["sku_id"] == "BQ-ACTIVE-STORAGE-US-CENTRAL1"


def test_bigquery_multi_region_us_sku_selected(populated_bq_db: str) -> None:
    """Verify US multi-region selection."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"active_storage_gb": 100.0},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "active_storage")
    assert storage_map["sku_id"] == "BQ-ACTIVE-STORAGE-US"


def test_bigquery_unresolvable_region_reported_unpriced(populated_bq_db: str) -> None:
    """Verify that unsupported region reports unpriced."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-1",
        service="bigquery",
        kind="bigquery_dataset",
        region="mars-east1",
        usage={"active_storage_gb": 100.0},
    )
    mapper = GcpSkuMapper(populated_bq_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert unpriced[0]["reason"] == "No matching active storage SKU found for region 'mars-east1'"
