# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.service import estimate_infrastructure
from gcp_billing_mcp.core.validate import validate_resource_model


@pytest.fixture
def populated_tier1_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with mock SKUs for GCE, SQL, GCS, GKE, and BQ."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load BQ mock SKUs
    with Path("tests/fixtures/bq_skus.json").open() as f:
        bq_skus = json.load(f)

    # Load GCS mock SKUs
    with Path("tests/fixtures/gcs_skus.json").open() as f:
        gcs_skus = json.load(f)

    # Load GKE mock SKUs
    with Path("tests/fixtures/gke_skus.json").open() as f:
        gke_skus = json.load(f)

    # Load Cloud SQL mock SKUs
    with Path("tests/fixtures/cloud_sql_skus.json").open() as f:
        sql_skus = json.load(f)

    # VM (GCE) mock SKUs
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

    # Combine and de-duplicate (remove Metadata citations if any)
    all_skus = bq_skus + gcs_skus + gke_skus + sql_skus + gce_skus
    clean_skus = []
    seen_sku_ids = set()
    for s in all_skus:
        if s["sku_id"] != "METADATA-CITATION" and s["sku_id"] not in seen_sku_ids:
            clean_skus.append(s)
            seen_sku_ids.add(s["sku_id"])

    update_cache(temp_db_path, "gcp", clean_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


@pytest.fixture
def combined_model() -> ResourceModel:
    """Create a ResourceModel featuring one of each Tier 1 resource with explicit usage."""
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
                "usage": {
                    "size_gb": 100.0,
                    "monthly_class_a_ops": 1000000.0,
                    "monthly_class_b_ops": 0,
                    "monthly_egress_gb": 0,
                    "monthly_retrieval_gb": 0,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "gke-1",
                "service": "container",
                "kind": "gke_cluster",
                "region": "us-central1",
                "attributes": {
                    "node_count": 3,
                    "machine_type": "e2-standard-4",
                    "disk_size_gb": 100,
                    "disk_type": "pd-standard",
                },
                "usage": {"runtime_hours_per_month": 730},
            },
            {
                "provider": "gcp",
                "resource_id": "sql-1",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "database_version": "MYSQL_8_0",
                    "edition": "ENTERPRISE",
                    "availability_type": "ZONAL",
                    "disk_type": "PD_SSD",
                    "disk_size_gb": 100,
                },
                "usage": {"runtime_hours_per_month": 730},
            },
            {
                "provider": "gcp",
                "resource_id": "dataset-1",
                "service": "bigquery",
                "kind": "bigquery_dataset",
                "region": "us",
                "usage": {
                    "active_storage_gb": 1000.0,
                    "long_term_storage_gb": 0,
                    "monthly_query_tb": 10.0,
                    "monthly_streaming_gb": 0,
                },
            },
        ]
    }
    return ResourceModel(**data)


def test_full_tier1_validate_returns_valid_for_combined_model(
    combined_model: ResourceModel,
) -> None:
    """Verify that the combined resource model validates without errors."""
    res = validate_resource_model(combined_model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_full_tier1_estimate_unpriced_list_empty_for_well_formed_model(
    populated_tier1_db: str, combined_model: ResourceModel
) -> None:
    """Verify that a fully specified Tier 1 model has no unpriced items."""
    est = estimate_infrastructure(populated_tier1_db, combined_model)
    assert len(est.unpriced) == 0


def test_full_tier1_estimate_all_services_present_in_line_items(
    populated_tier1_db: str, combined_model: ResourceModel
) -> None:
    """Verify that GCE, GCS, GKE, SQL, and BQ all contribute to line items and match golden total."""
    est = estimate_infrastructure(populated_tier1_db, combined_model)

    with Path("tests/fixtures/tier1_combined_estimate_golden.json").open() as f:
        golden = json.load(f)

    # Check total cost matches golden
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]

    # Verify that all 5 resource_ids appear in the line items
    resource_ids = {item.resource_id for item in est.line_items}
    assert resource_ids == {"vm-1", "bucket-1", "gke-1", "sql-1", "dataset-1"}


def test_full_tier1_estimate_each_service_contributes_correct_subtotal(
    populated_tier1_db: str, combined_model: ResourceModel
) -> None:
    """Verify subtotals for each component resource are calculated correctly."""
    est = estimate_infrastructure(populated_tier1_db, combined_model)

    # Calculate subtotals
    subtotals = {}
    for item in est.line_items:
        subtotals[item.resource_id] = subtotals.get(item.resource_id, 0.0) + item.monthly_cost

    assert pytest.approx(subtotals["vm-1"], abs=1e-4) == 97.82876
    assert pytest.approx(subtotals["bucket-1"], abs=1e-4) == 7.00
    assert pytest.approx(subtotals["gke-1"], abs=1e-4) == 378.48628
    assert pytest.approx(subtotals["sql-1"], abs=1e-4) == 115.623
    assert pytest.approx(subtotals["dataset-1"], abs=1e-4) == 82.50
