# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.service import estimate_infrastructure
from gcp_cost_estimator.core.validate import validate_resource_model


@pytest.fixture
def populated_firestore_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Cloud Firestore SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/firestore_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    # GCE mock SKUs for combined tests
    gce_skus = [
        {
            "sku_id": "SKU-N2-CPU",
            "provider": "gcp",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core",
        },
        {
            "sku_id": "SKU-N2-RAM",
            "provider": "gcp",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram",
        },
    ]

    update_cache(temp_db_path, "gcp", mock_skus + gce_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


# ==========================================
# FS-1: Validation Tests
# ==========================================


def test_firestore_database_valid_native_mode() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-1",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
                "attributes": {
                    "database_type": "FIRESTORE_NATIVE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_firestore_database_valid_datastore_mode() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-2",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
                "attributes": {
                    "database_type": "DATASTORE_MODE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_firestore_database_unknown_type_flagged_as_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-3",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
                "attributes": {
                    "database_type": "INVALID_TYPE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("database_type" in w or "unrecognized" in w for w in result["warnings"])


def test_firestore_database_missing_location_produces_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-4",
                "service": "firestore",
                "kind": "firestore_database",
                "attributes": {
                    "database_type": "FIRESTORE_NATIVE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("region" in w.lower() for w in result["warnings"])


def test_firestore_database_location_normalised_to_gcp_region() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-5",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central",
                "attributes": {
                    "database_type": "FIRESTORE_NATIVE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].region == "us-central1"


def test_firestore_database_defaults_all_usage_with_assumptions() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-6",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    res = normalized.resources[0]
    assert res.usage["storage_gb"] == 1
    assert res.usage["monthly_reads"] == 500000
    assert res.usage["monthly_writes"] == 100000
    assert res.usage["monthly_deletes"] == 10000
    assert res.usage["monthly_egress_gb"] == 0


def test_firestore_database_free_tier_noted_in_assumptions() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-7",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    normalized = result["normalized_model"]
    assert any("Free tier" in a for a in normalized.resources[0].assumptions)


# ==========================================
# FS-2: SKU Mapping Tests
# ==========================================


def test_firestore_storage_sku_emitted(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-storage",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "FIRESTORE_NATIVE"},
        usage={"storage_gb": 10.0, "monthly_reads": 0, "monthly_writes": 0, "monthly_deletes": 0},
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FIRESTORE-STORAGE"
    assert mappings[0]["qty"] == 10.0


def test_firestore_reads_sku_emitted_qty_in_100k_units(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-reads",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "FIRESTORE_NATIVE"},
        usage={
            "storage_gb": 0.0,
            "monthly_reads": 500000,
            "monthly_writes": 0,
            "monthly_deletes": 0,
        },
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FIRESTORE-READS"
    assert mappings[0]["qty"] == 5.0


def test_firestore_writes_sku_emitted_qty_in_100k_units(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-writes",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "FIRESTORE_NATIVE"},
        usage={
            "storage_gb": 0.0,
            "monthly_reads": 0,
            "monthly_writes": 250000,
            "monthly_deletes": 0,
        },
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FIRESTORE-WRITES"
    assert mappings[0]["qty"] == 2.5


def test_firestore_deletes_sku_emitted_qty_in_100k_units(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-deletes",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "FIRESTORE_NATIVE"},
        usage={
            "storage_gb": 0.0,
            "monthly_reads": 0,
            "monthly_writes": 0,
            "monthly_deletes": 10000,
        },
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FIRESTORE-DELETES"
    assert mappings[0]["qty"] == 0.1


def test_firestore_zero_reads_no_reads_sku(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-zero-reads",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "FIRESTORE_NATIVE"},
        usage={
            "storage_gb": 1.0,
            "monthly_reads": 0,
            "monthly_writes": 10000,
            "monthly_deletes": 1000,
        },
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert not any(m["component"] == "reads" for m in mappings)


def test_firestore_egress_sku_emitted_when_nonzero(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-egress",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "FIRESTORE_NATIVE"},
        usage={
            "storage_gb": 0.0,
            "monthly_reads": 0,
            "monthly_writes": 0,
            "monthly_deletes": 0,
            "monthly_egress_gb": 10,
        },
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FIRESTORE-EGRESS"
    assert mappings[0]["qty"] == 10.0


def test_firestore_datastore_mode_uses_same_skus_as_native(populated_firestore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="firestore-datastore",
        service="firestore",
        kind="firestore_database",
        region="us-central1",
        attributes={"database_type": "DATASTORE_MODE"},
        usage={
            "storage_gb": 5.0,
            "monthly_reads": 100000,
            "monthly_writes": 50000,
            "monthly_deletes": 5000,
        },
    )
    mapper = GcpSkuMapper(populated_firestore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 4


# ==========================================
# FS-3: Cost Calculation Tests
# ==========================================


def test_firestore_cost_cases(populated_firestore_db: str) -> None:
    with Path("tests/fixtures/firestore_cost_cases.json").open() as f:
        cases = json.load(f)

    for case in cases:
        res = Resource(
            provider="gcp",
            resource_id="firestore-test",
            service="firestore",
            kind="firestore_database",
            region=case["region"],
            attributes={
                "database_type": "FIRESTORE_NATIVE",
            },
            usage={
                "storage_gb": case["storage_gb"],
                "monthly_reads": case["monthly_reads"],
                "monthly_writes": case["monthly_writes"],
                "monthly_deletes": case["monthly_deletes"],
            },
        )
        model = ResourceModel(resources=[res])
        est = estimate_infrastructure(populated_firestore_db, model)

        assert len(est.unpriced) == 0
        stor_item = next(item for item in est.line_items if item.component == "storage")
        assert pytest.approx(stor_item.monthly_cost, abs=1e-4) == case["expected_storage_cost"]

        reads_item = next(item for item in est.line_items if item.component == "reads")
        assert pytest.approx(reads_item.monthly_cost, abs=1e-4) == case["expected_reads_cost"]

        writes_item = next(item for item in est.line_items if item.component == "writes")
        assert pytest.approx(writes_item.monthly_cost, abs=1e-4) == case["expected_writes_cost"]

        deletes_item = next(item for item in est.line_items if item.component == "deletes")
        assert pytest.approx(deletes_item.monthly_cost, abs=1e-4) == case["expected_deletes_cost"]

        assert pytest.approx(est.monthly_total, abs=1e-4) == case["expected_total"]


# ==========================================
# FS-4: End-to-End Estimation Tests
# ==========================================


def test_estimate_firestore_native_golden_fixture(populated_firestore_db: str) -> None:
    data = {
        "resources": [
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
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_firestore_db, model)

    with Path("tests/fixtures/firestore_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_firestore_zero_usage_empty_line_items_not_error(
    populated_firestore_db: str,
) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-zero",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
                "attributes": {
                    "database_type": "FIRESTORE_NATIVE",
                },
                "usage": {
                    "storage_gb": 0,
                    "monthly_reads": 0,
                    "monthly_writes": 0,
                    "monthly_deletes": 0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_firestore_db, model)
    assert len(est.line_items) == 0
    assert est.monthly_total == 0.0


def test_estimate_firestore_defaults_recorded_in_assumptions(populated_firestore_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-1",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_firestore_db, model)
    assert any("Defaulted storage_gb to 1" in a for a in est.assumptions)
    assert any("Defaulted monthly_reads to 500000" in a for a in est.assumptions)


def test_estimate_firestore_combined_with_gce_instance(populated_firestore_db: str) -> None:
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
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_firestore_db, model)
    # GCE CPU is 138.7. GCE RAM is 0.1008. Total GCE is 138.8008
    # Firestore cost is 0.3972
    # The expected total cost is 139.198
    assert pytest.approx(est.monthly_total, abs=1e-4) == 139.198
    assert len(est.line_items) == 6


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_firestore_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "firestore-1",
                "service": "firestore",
                "kind": "firestore_database",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_firestore_db, model)
    assert est.disclaimer != ""
    assert "list price only" in est.disclaimer.lower()
    assert est.pricing_snapshot == "2026-06-10T12:00:00Z"
