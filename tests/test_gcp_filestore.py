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
def populated_filestore_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Filestore SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/filestore_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-15T12:00:00Z")
    return temp_db_path


# ==========================================
# Validation & Normalisation Tests
# ==========================================

def test_validate_filestore_valid_instance() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nfs-1",
                "service": "filestore",
                "kind": "google_filestore_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "BASIC_HDD",
                    "capacity_gb": 1024,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert len(result["warnings"]) == 0


def test_validate_filestore_invalid_tier_raises_error() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nfs-invalid",
                "service": "filestore",
                "kind": "google_filestore_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "INVALID_TIER",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    assert any("invalid Filestore tier" in e for e in result["errors"])


def test_validate_filestore_capacity_below_minimum_warns() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nfs-small",
                "service": "filestore",
                "kind": "google_filestore_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "BASIC_HDD",
                    "capacity_gb": 500,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("below tier minimum" in w for w in result["warnings"])


def test_validate_filestore_normalises_tier_to_uppercase() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nfs-norm",
                "service": "filestore",
                "kind": "google_filestore_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "basic_hdd",
                    "capacity_gb": "2048",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["tier"] == "BASIC_HDD"
    assert isinstance(normalized.resources[0].attributes["capacity_gb"], float)
    assert normalized.resources[0].attributes["capacity_gb"] == 2048.0


def test_validate_filestore_custom_performance_adds_unpriced() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nfs-perf",
                "service": "filestore",
                "kind": "google_filestore_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "ZONAL",
                    "capacity_gb": 1024,
                    "custom_performance_enabled": True,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["unpriced"]) > 0
    assert any("Custom Performance" in item["reason"] for item in result["unpriced"])


# ==========================================
# SKU Mapping & Cost Calculation Tests
# ==========================================

def test_filestore_basic_hdd_1tib_cost(populated_filestore_db: str) -> None:
    # 1024 GiB * $0.000219178 * 730 hr = $163.854...
    # Waived instance fee because capacity >= 1024 GiB
    res = Resource(
        provider="gcp",
        resource_id="nfs-share",
        service="filestore",
        kind="google_filestore_instance",
        region="us-central1",
        attributes={"tier": "BASIC_HDD", "capacity_gb": 1024.0},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_filestore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FILESTORE-BASIC-HDD-CAPACITY"
    assert mappings[0]["qty"] == 1024 * 730
    assert any("backup" in u["reason"] for u in unpriced)


def test_filestore_basic_hdd_under_1tib_includes_instance_fee(populated_filestore_db: str) -> None:
    # 500 GiB * $0.000219178 * 730 hr = $80.00
    # + Instance fee: 730 * $0.045205479 = $33.00
    # Total = $113.00
    res = Resource(
        provider="gcp",
        resource_id="nfs-small",
        service="filestore",
        kind="google_filestore_instance",
        region="us-central1",
        attributes={"tier": "BASIC_HDD", "capacity_gb": 500.0},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_filestore_db)
    mappings, _ = mapper.map_resource_to_skus(res)
    assert len(mappings) == 2
    
    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "SKU-FILESTORE-BASIC-HDD-CAPACITY"
    assert storage_map["qty"] == 500 * 730

    compute_map = next(m for m in mappings if m["component"] == "compute")
    assert compute_map["sku_id"] == "SKU-FILESTORE-BASIC-HDD-FEE"
    assert compute_map["qty"] == 730


def test_filestore_zonal_2tib_cost(populated_filestore_db: str) -> None:
    # 2048 GiB * $0.000342466 * 730 hr = $511.71...
    res = Resource(
        provider="gcp",
        resource_id="nfs-zonal",
        service="filestore",
        kind="google_filestore_instance",
        region="us-central1",
        attributes={"tier": "ZONAL", "capacity_gb": 2048.0},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_filestore_db)
    mappings, _ = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FILESTORE-ZONAL-CAPACITY"
    assert mappings[0]["qty"] == 2048 * 730


def test_filestore_regional_rate(populated_filestore_db: str) -> None:
    # 1024 GiB * $0.000616438 * 730 hr = $460.47...
    res = Resource(
        provider="gcp",
        resource_id="nfs-regional",
        service="filestore",
        kind="google_filestore_instance",
        region="us-central1",
        attributes={"tier": "REGIONAL", "capacity_gb": 1024.0},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_filestore_db)
    mappings, _ = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-FILESTORE-REGIONAL-CAPACITY"


def test_estimate_filestore_e2e(populated_filestore_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nfs-e2e",
                "service": "filestore",
                "kind": "google_filestore_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "BASIC_HDD",
                    "capacity_gb": 1024,
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                }
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_filestore_db, model)
    assert est.monthly_total == pytest.approx(163.84, abs=1e-2)
    assert len(est.line_items) == 1
    assert est.line_items[0].component == "storage"
    assert len(est.unpriced) == 1
