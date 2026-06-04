# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.compare import suggest_cheaper_machine_types
from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache


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


def test_suggest_bigquery_long_term_cheaper_than_active_for_same_volume(
    populated_bq_db: str,
) -> None:
    """Verify that suggesting long-term storage for active volume shows savings."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-test",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"active_storage_gb": 100.0, "long_term_storage_gb": 0.0},
    )
    suggestions = suggest_cheaper_machine_types(populated_bq_db, resource)
    assert len(suggestions) == 1
    sug = suggestions[0]
    assert "long-term" in sug["recommendation"].lower()
    assert pytest.approx(sug["monthly_cost"], abs=1e-4) == 1.0
    assert pytest.approx(sug["monthly_savings"], abs=1e-4) == 1.0


def test_suggest_bigquery_active_only_reports_long_term_saving(populated_bq_db: str) -> None:
    """Verify that suggesting long-term storage is only returned if active storage exists."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-test",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"active_storage_gb": 500.0, "long_term_storage_gb": 0.0},
    )
    suggestions = suggest_cheaper_machine_types(populated_bq_db, resource)
    assert len(suggestions) == 1
    sug = suggestions[0]
    # Active cost for 500 GB is 10.0
    # Long-term cost for 500 GB is 5.0
    # Savings is 5.0
    assert pytest.approx(sug["monthly_cost"], abs=1e-4) == 5.0
    assert pytest.approx(sug["monthly_savings"], abs=1e-4) == 5.0


def test_suggest_bigquery_already_long_term_no_suggestion(populated_bq_db: str) -> None:
    """Verify that if all storage is already long-term, no suggestions are returned."""
    resource = Resource(
        provider="gcp",
        resource_id="dataset-test",
        service="bigquery",
        kind="bigquery_dataset",
        region="us",
        usage={"active_storage_gb": 0.0, "long_term_storage_gb": 100.0},
    )
    suggestions = suggest_cheaper_machine_types(populated_bq_db, resource)
    assert len(suggestions) == 0
