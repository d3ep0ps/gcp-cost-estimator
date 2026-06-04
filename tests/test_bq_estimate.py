# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.service import estimate_infrastructure


@pytest.fixture
def populated_combined_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with BigQuery, GCS, and GCE mock SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load BQ SKUs
    with Path("tests/fixtures/bq_skus.json").open() as f:
        bq_skus = json.load(f)
    bq_skus = [s for s in bq_skus if s["sku_id"] != "METADATA-CITATION"]

    # Load GCS SKUs
    with Path("tests/fixtures/gcs_skus.json").open() as f:
        gcs_skus = json.load(f)
    gcs_skus = [s for s in gcs_skus if s["sku_id"] != "METADATA-CITATION"]

    # GCE mock SKUs
    gce_skus = [
        {
            "sku_id": "SKU-E2-CPU",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.021811,
            "sku_group": "CPU",
            "description": "E2 Instance Core",
        },
        {
            "sku_id": "SKU-E2-RAM",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.h",
            "unit_price": 0.002923,
            "sku_group": "RAM",
            "description": "E2 Instance Ram",
        },
    ]

    combined_skus = bq_skus + gcs_skus + gce_skus
    update_cache(temp_db_path, "gcp", combined_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_estimate_bigquery_dataset_golden_fixture(populated_combined_db: str) -> None:
    """Verify BQ dataset estimate matches the golden fixture exactly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dataset-golden",
                "service": "bigquery",
                "kind": "bigquery_dataset",
                "region": "us",
                "usage": {
                    "active_storage_gb": 1000.0,
                    "long_term_storage_gb": 0.0,
                    "monthly_query_tb": 10.0,
                    "monthly_streaming_gb": 0.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    with Path("tests/fixtures/bq_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_bigquery_zero_usage_returns_empty_line_items_not_error(
    populated_combined_db: str,
) -> None:
    """Verify that zero usage fields result in zero cost and no line items."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dataset-zero",
                "service": "bigquery",
                "kind": "bigquery_dataset",
                "region": "us",
                "usage": {
                    "active_storage_gb": 0.0,
                    "long_term_storage_gb": 0.0,
                    "monthly_query_tb": 0.0,
                    "monthly_streaming_gb": 0.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    assert est.monthly_total == 0.0
    assert len(est.line_items) == 0


def test_estimate_bigquery_query_only_no_storage(populated_combined_db: str) -> None:
    """Verify queries-only scenario calculates properly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dataset-query-only",
                "service": "bigquery",
                "kind": "bigquery_dataset",
                "region": "us",
                "usage": {
                    "active_storage_gb": 0.0,
                    "long_term_storage_gb": 0.0,
                    "monthly_query_tb": 5.0,
                    "monthly_streaming_gb": 0.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    assert pytest.approx(est.monthly_total, abs=1e-4) == 31.25
    assert len(est.line_items) == 1
    assert est.line_items[0].component == "query_scan"


def test_estimate_bigquery_combined_with_gce_and_gcs(populated_combined_db: str) -> None:
    """Verify pricing a multi-service model (GCE VM + GCS bucket + BQ dataset)."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "e2-standard-4"},
                "usage": {"runtime_hours_per_month": 730},
            },
            {
                "provider": "gcp",
                "resource_id": "bucket-1",
                "service": "storage",
                "kind": "gcs_bucket",
                "region": "us-central1",
                "attributes": {"storage_class": "STANDARD"},
                "usage": {"size_gb": 100.0, "monthly_class_a_ops": 10000.0},
            },
            {
                "provider": "gcp",
                "resource_id": "dataset-1",
                "service": "bigquery",
                "kind": "bigquery_dataset",
                "region": "us-central1",
                "usage": {"active_storage_gb": 200.0, "monthly_query_tb": 2.0},
            },
        ]
    }
    # Compute: e2-standard-4 = 4 vCPU, 16 GB RAM.
    # CPU Cost = 4 * 730 * 0.021811 = 63.68812
    # RAM Cost = 16 * 730 * 0.002923 = 34.14064
    # VM Total = 97.82876
    # GCS: 100 GB standard storage = 100 * 0.02 = 2.0
    # Class A ops = 10000 / 10000 = 1.0 * 0.05 = 0.05
    # GCS missing usage fields (Class B ops = 100,000, egress = 10 GB) are defaulted:
    # Class B ops = 100,000 / 10,000 = 10 * 0.004 = 0.04
    # Egress = 10 * 0.12 = 1.20
    # GCS Total = 2.05 + 1.24 = 3.29
    # BQ: 200 GB active storage = 200 * 0.02 = 4.0
    # Queries = 2 TB * 6.25 = 12.50
    # BQ Total = 16.50
    # Grand Total = 97.82876 + 3.29 + 16.50 = 117.61876
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    assert pytest.approx(est.monthly_total, abs=1e-4) == 117.61876


def test_estimate_includes_disclaimer_snapshot_ts_and_free_tier_assumption(
    populated_combined_db: str,
) -> None:
    """Verify that disclaimer, snapshot timestamp, and BQ free tier assumptions are present."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dataset-test",
                "service": "bigquery",
                "kind": "bigquery_dataset",
                "region": "us",
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    # Check disclaimer and snapshot ts fields
    assert "List price only" in est.disclaimer
    assert est.pricing_snapshot == "2026-06-03T12:00:00Z"

    # Check that BQ free tier assumptions are present in the list
    all_assumptions = "\n".join(est.assumptions)
    assert "Free tier (10 GB storage, 1 TB queries/month) not applied" in all_assumptions
