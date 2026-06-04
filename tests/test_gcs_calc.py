import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.calc import calculate_line_items, calculate_totals
from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_gcs_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static GCS SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/gcs_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_gcs_storage_gb_month_cost_matches_fixture(populated_gcs_db: str) -> None:
    """Verify GCS line items and math calculate correctly using fixtures."""
    with Path("tests/fixtures/gcs_cost_cases.json").open() as f:
        cases = json.load(f)

    # Filter out metadata
    cases = [c for c in cases if "label" in c]

    mapper = GcpSkuMapper(populated_gcs_db)

    for case in cases:
        resource = Resource(
            provider="gcp",
            resource_id="bucket-test",
            service="storage",
            kind="gcs_bucket",
            region=case["region"],
            attributes={"storage_class": case["storage_class"]},
            usage={
                "size_gb": case["size_gb"],
                "monthly_class_a_ops": case["monthly_class_a_ops"],
                "monthly_class_b_ops": case["monthly_class_b_ops"],
                "monthly_egress_gb": case["monthly_egress_gb"],
                "monthly_retrieval_gb": case["monthly_retrieval_gb"],
            },
        )

        mappings, unpriced = mapper.map_resource_to_skus(resource)
        assert len(unpriced) == 0

        line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
        total = calculate_totals(line_items)

        # Check total cost
        assert pytest.approx(total, abs=1e-4) == case["expected_total"]

        # Check individual component costs
        if case["size_gb"] > 0:
            storage_item = next(item for item in line_items if item.component == "storage")
            assert (
                pytest.approx(storage_item.monthly_cost, abs=1e-4) == case["expected_storage_cost"]
            )

        if case["monthly_class_a_ops"] > 0:
            class_a_item = next(item for item in line_items if item.component == "class_a_ops")
            assert (
                pytest.approx(class_a_item.monthly_cost, abs=1e-4)
                == case["expected_class_a_ops_cost"]
            )

        if case["monthly_class_b_ops"] > 0:
            class_b_item = next(item for item in line_items if item.component == "class_b_ops")
            assert (
                pytest.approx(class_b_item.monthly_cost, abs=1e-4)
                == case["expected_class_b_ops_cost"]
            )

        if case["monthly_egress_gb"] > 0:
            egress_item = next(item for item in line_items if item.component == "egress")
            assert pytest.approx(egress_item.monthly_cost, abs=1e-4) == case["expected_egress_cost"]

        if case["monthly_retrieval_gb"] > 0:
            retrieval_item = next(item for item in line_items if item.component == "retrieval")
            assert (
                pytest.approx(retrieval_item.monthly_cost, abs=1e-4)
                == case["expected_retrieval_cost"]
            )


def test_gcs_zero_usage_fields_produce_zero_cost_not_error(populated_gcs_db: str) -> None:
    """Verify that zero usage fields result in zero priced line items and zero cost total."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-zero",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={
            "size_gb": 0.0,
            "monthly_class_a_ops": 0.0,
            "monthly_class_b_ops": 0.0,
            "monthly_egress_gb": 0.0,
            "monthly_retrieval_gb": 0.0,
        },
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)
    assert len(unpriced) == 0
    assert len(mappings) == 0  # Zero mappings since zero usage is skipped

    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    total = calculate_totals(line_items)
    assert total == 0.0
    assert len(line_items) == 0
