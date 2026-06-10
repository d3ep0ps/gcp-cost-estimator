# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.service import estimate_infrastructure
from gcp_cost_estimator.core.validate import validate_resource_model


@pytest.fixture
def populated_tier3_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with mock SKUs for Spanner, Firestore, Memorystore, Bigtable, and AlloyDB."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load Spanner mock SKUs
    with Path("tests/fixtures/spanner_skus.json").open() as f:
        spanner_skus = json.load(f)

    # Load Firestore mock SKUs
    with Path("tests/fixtures/firestore_skus.json").open() as f:
        firestore_skus = json.load(f)

    # Load Memorystore mock SKUs
    with Path("tests/fixtures/memorystore_skus.json").open() as f:
        memorystore_skus = json.load(f)

    # Load Bigtable mock SKUs
    with Path("tests/fixtures/bigtable_skus.json").open() as f:
        bigtable_skus = json.load(f)

    # Load AlloyDB mock SKUs
    with Path("tests/fixtures/alloydb_skus.json").open() as f:
        alloydb_skus = json.load(f)

    # Combine and de-duplicate
    all_skus = spanner_skus + firestore_skus + memorystore_skus + bigtable_skus + alloydb_skus
    clean_skus = []
    seen_sku_ids = set()
    for s in all_skus:
        if s["sku_id"] != "METADATA-CITATION" and s["sku_id"] not in seen_sku_ids:
            clean_skus.append(s)
            seen_sku_ids.add(s["sku_id"])

    update_cache(temp_db_path, "gcp", clean_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


@pytest.fixture
def tier3_combined_model() -> ResourceModel:
    """Create a ResourceModel featuring one of each Tier 3 database resource with explicit usage."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-golden",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                    "edition": "STANDARD",
                    "processing_units": 100,
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                    "storage_gb": 10,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "firestore-golden",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
                "attributes": {
                    "database_type": "FIRESTORE_NATIVE",
                },
                "usage": {
                    "storage_gb": 1.0,
                    "monthly_reads": 500000,
                    "monthly_writes": 100000,
                    "monthly_deletes": 10000,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "redis-golden",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5.0,
                    "tier": "BASIC",
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "valkey-golden",
                "service": "memorystore",
                "kind": "memorystore_instance",
                "region": "us-central1",
                "attributes": {
                    "node_type": "STANDARD_SMALL",
                    "shard_count": 1,
                    "mode": "STANDALONE",
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "bigtable-golden",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                    "clusters": [
                        {
                            "cluster_id": "us-central1-cluster",
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                            "storage_type": "SSD",
                        }
                    ],
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                    "storage_gb_per_cluster": 100.0,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "alloydb-cluster-golden",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
                "attributes": {},
                "usage": {
                    "storage_gb": 100.0,
                    "backup_enabled": False,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-golden",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRIMARY",
                    "cpu_count": 4,
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                },
            },
        ]
    }
    return ResourceModel(**data)


def test_full_tier3_validate_returns_valid_for_combined_model(
    tier3_combined_model: ResourceModel,
) -> None:
    """Verify that the combined resource model validates without errors."""
    res = validate_resource_model(tier3_combined_model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_full_tier3_estimate_unpriced_list_empty_for_well_formed_model(
    populated_tier3_db: str, tier3_combined_model: ResourceModel
) -> None:
    """Verify that a fully specified Tier 3 model has no unpriced items."""
    est = estimate_infrastructure(populated_tier3_db, tier3_combined_model)
    assert len(est.unpriced) == 0


def test_full_tier3_estimate_all_services_present_in_line_items(
    populated_tier3_db: str, tier3_combined_model: ResourceModel
) -> None:
    """Verify that Spanner, Firestore, Memorystore (both Redis & Valkey), Bigtable, and AlloyDB contribute to line items and match golden total."""
    est = estimate_infrastructure(populated_tier3_db, tier3_combined_model)

    with Path("tests/fixtures/tier3_combined_estimate_golden.json").open() as f:
        golden = json.load(f)

    # Check total cost matches golden
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]

    # Verify that all 7 resource_ids appear in the line items
    resource_ids = {item.resource_id for item in est.line_items}
    assert resource_ids == {
        "spanner-golden",
        "firestore-golden",
        "redis-golden",
        "valkey-golden",
        "bigtable-golden",
        "alloydb-cluster-golden",
        "alloydb-instance-golden",
    }


def test_full_tier3_estimate_each_service_contributes_correct_subtotal(
    populated_tier3_db: str, tier3_combined_model: ResourceModel
) -> None:
    """Verify subtotals for each component resource are calculated correctly."""
    est = estimate_infrastructure(populated_tier3_db, tier3_combined_model)

    # Calculate subtotals
    subtotals = {}
    for item in est.line_items:
        subtotals[item.resource_id] = subtotals.get(item.resource_id, 0.0) + item.monthly_cost

    assert pytest.approx(subtotals["spanner-golden"], abs=1e-4) == 9.57
    assert pytest.approx(subtotals["firestore-golden"], abs=1e-4) == 0.3972
    assert pytest.approx(subtotals["redis-golden"], abs=1e-4) == 49.275
    assert pytest.approx(subtotals["valkey-golden"], abs=1e-4) == 40.15
    assert pytest.approx(subtotals["bigtable-golden"], abs=1e-4) == 1440.50
    assert pytest.approx(subtotals["alloydb-cluster-golden"], abs=1e-4) == 13.75
    assert pytest.approx(subtotals["alloydb-instance-golden"], abs=1e-4) == 322.368


def test_full_tier3_combined_with_tier1_services(
    temp_db_path: str, tier3_combined_model: ResourceModel
) -> None:
    """Verify that a combined model with both Tier 1 and Tier 3 services works perfectly in a single cache database."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load all mock SKU JSON files
    sku_files = [
        "spanner_skus.json",
        "firestore_skus.json",
        "memorystore_skus.json",
        "bigtable_skus.json",
        "alloydb_skus.json",
        "bq_skus.json",
        "gcs_skus.json",
        "gke_skus.json",
        "cloud_sql_skus.json",
    ]

    all_skus = []
    for sf in sku_files:
        with Path("tests/fixtures", sf).open() as f:
            all_skus.extend(json.load(f))

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
    all_skus.extend(gce_skus)

    # De-duplicate
    clean_skus = []
    seen_sku_ids = set()
    for s in all_skus:
        if s["sku_id"] != "METADATA-CITATION" and s["sku_id"] not in seen_sku_ids:
            clean_skus.append(s)
            seen_sku_ids.add(s["sku_id"])

    # Update cache
    update_cache(temp_db_path, "gcp", clean_skus, "2026-06-10T12:00:00Z")

    # Construct combined Tier 1 and Tier 3 resources model
    tier1_data = [
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
    ]

    all_resources = list(tier3_combined_model.resources)
    for r in tier1_data:
        all_resources.append(r)

    combined_model = ResourceModel(resources=all_resources)

    # Validate model
    val_res = validate_resource_model(combined_model)
    assert val_res["valid"] is True

    # Estimate cost
    est = estimate_infrastructure(temp_db_path, combined_model)
    assert len(est.unpriced) == 0

    # Total expected is Tier 3 total (1876.0102) + VM total (97.82876) + Bucket total (7.00) = 1980.83896
    assert pytest.approx(est.monthly_total, abs=1e-4) == 1980.83896
