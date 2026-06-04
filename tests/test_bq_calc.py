import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.calc import calculate_line_items, calculate_totals
from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper


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


def test_bigquery_cost_math_matches_fixtures(populated_bq_db: str) -> None:
    """Verify BigQuery cost math against expected fixture calculations."""
    with Path("tests/fixtures/bq_cost_cases.json").open() as f:
        cases = json.load(f)

    mapper = GcpSkuMapper(populated_bq_db)

    for case in cases:
        resource = Resource(
            provider="gcp",
            resource_id="bq-dataset-test",
            service="bigquery",
            kind="bigquery_dataset",
            region="us",
            attributes={},
            usage={
                "active_storage_gb": case["active_storage_gb"],
                "long_term_storage_gb": case["long_term_storage_gb"],
                "monthly_query_tb": case["monthly_query_tb"],
                "monthly_streaming_gb": case["monthly_streaming_gb"],
            },
        )

        mappings, unpriced = mapper.map_resource_to_skus(resource)
        assert len(unpriced) == 0

        line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
        total = calculate_totals(line_items)

        # Check total cost
        assert pytest.approx(total, abs=1e-4) == case["expected_total"]

        # Check individual components
        if case["active_storage_gb"] > 0:
            item = next(i for i in line_items if i.component == "active_storage")
            assert pytest.approx(item.monthly_cost, abs=1e-4) == case["expected_active_cost"]

        if case["long_term_storage_gb"] > 0:
            item = next(i for i in line_items if i.component == "long_term_storage")
            assert pytest.approx(item.monthly_cost, abs=1e-4) == case["expected_long_term_cost"]

        if case["monthly_query_tb"] > 0:
            item = next(i for i in line_items if i.component == "query_scan")
            assert pytest.approx(item.monthly_cost, abs=1e-4) == case["expected_query_cost"]

        if case["monthly_streaming_gb"] > 0:
            item = next(i for i in line_items if i.component == "streaming_insert")
            assert pytest.approx(item.monthly_cost, abs=1e-4) == case["expected_streaming_cost"]
