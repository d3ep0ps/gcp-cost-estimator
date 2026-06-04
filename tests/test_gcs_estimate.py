# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.service import estimate_infrastructure


@pytest.fixture
def populated_combined_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with both GCS and GCE mock SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load GCS SKUs
    with Path("tests/fixtures/gcs_skus.json").open() as f:
        gcs_skus = json.load(f)
    gcs_skus = [s for s in gcs_skus if s["sku_id"] != "METADATA-CITATION"]

    # GCE mock SKUs
    gce_skus = [
        {
            "sku_id": "SKU-N2-CPU",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core",
        },
        {
            "sku_id": "SKU-N2-RAM",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram",
        },
    ]

    combined_skus = gcs_skus + gce_skus
    update_cache(temp_db_path, "gcp", combined_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_estimate_gcs_standard_golden_fixture(populated_combined_db: str) -> None:
    """Verify standard bucket cost estimate matches the golden fixture exactly."""
    # 100 GB Standard, us-central1, 1M Class A ops
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bucket-golden",
                "service": "storage",
                "kind": "gcs_bucket",
                "region": "us-central1",
                "attributes": {"storage_class": "STANDARD"},
                "usage": {
                    "size_gb": 100.0,
                    "monthly_class_a_ops": 1000000.0,
                    "monthly_class_b_ops": 0.0,
                    "monthly_egress_gb": 0.0,
                    "monthly_retrieval_gb": 0.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    with Path("tests/fixtures/gcs_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_gcs_nearline_with_retrieval_fee(populated_combined_db: str) -> None:
    """Verify Nearline storage cost calculation, including retrieval and egress."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bucket-nearline",
                "service": "storage",
                "kind": "gcs_bucket",
                "region": "us-central1",
                "attributes": {"storage_class": "NEARLINE"},
                "usage": {
                    "size_gb": 500.0,
                    "monthly_class_a_ops": 0.0,
                    "monthly_class_b_ops": 0.0,
                    "monthly_egress_gb": 10.0,
                    "monthly_retrieval_gb": 50.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    assert est.monthly_total == 6.70
    assert len(est.unpriced) == 0
    assert len(est.line_items) == 3


def test_estimate_gcs_zero_usage_defaults_reported_in_assumptions(
    populated_combined_db: str,
) -> None:
    """Verify that when no usage/attributes are specified, representative defaults are applied and logged in assumptions."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bucket-default",
                "service": "storage",
                "kind": "gcs_bucket",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    # Standard defaults: 100 GB Standard, 10k A ops, 100k B ops, 10 GB egress.
    # Storage standard = 100 * 0.02 = 2.0
    # Class A = (10k / 10k) * 0.05 = 0.05
    # Class B = (100k / 10k) * 0.004 = 0.04
    # Egress = 10 * 0.12 = 1.20
    # Expected total = 2.0 + 0.05 + 0.04 + 1.20 = 3.29
    assert pytest.approx(est.monthly_total, abs=1e-4) == 3.29
    assert len(est.unpriced) == 0
    assert len(est.line_items) == 4

    # Assumptions should contain the defaults description
    assert any("Defaulted storage_class to STANDARD" in a for a in est.assumptions)
    assert any("Defaulted size_gb to 100" in a for a in est.assumptions)
    assert any("Defaulted monthly_class_a_ops to 10000" in a for a in est.assumptions)
    assert any("Defaulted monthly_class_b_ops to 100000" in a for a in est.assumptions)
    assert any("Defaulted monthly_egress_gb to 10" in a for a in est.assumptions)


def test_estimate_gcs_combined_with_gce_instance(populated_combined_db: str) -> None:
    """Verify combined model estimates GCE and GCS together correctly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
                "usage": {"runtime_hours_per_month": 730.0},
            },
            {
                "provider": "gcp",
                "resource_id": "bucket-1",
                "service": "storage",
                "kind": "gcs_bucket",
                "region": "us-central1",
                "attributes": {"storage_class": "STANDARD"},
                "usage": {
                    "size_gb": 100.0,
                    "monthly_class_a_ops": 1000000.0,
                    "monthly_class_b_ops": 0.0,
                    "monthly_egress_gb": 0.0,
                    "monthly_retrieval_gb": 0.0,
                },
            },
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    # GCE cost: vcpu (0.0475 * 4 * 730 = 138.7) + ram (0.0063 * 16 = 0.1008) = 138.8008
    # GCS cost: storage (100 * 0.02 = 2.0) + Class A (1M / 10k * 0.05 = 5.0) = 7.0
    # Combined expected total = 138.8008 + 7.0 = 145.8008
    assert pytest.approx(est.monthly_total, abs=1e-4) == 145.8008
    assert len(est.unpriced) == 0
    assert len(est.line_items) == 4


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_combined_db: str) -> None:
    """Verify disclaimer and snapshot metadata are attached to GCS estimates."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bucket-1",
                "service": "storage",
                "kind": "gcs_bucket",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    assert est.disclaimer != ""
    assert "list price only" in est.disclaimer.lower()
    assert est.pricing_snapshot == "2026-06-03T12:00:00Z"
