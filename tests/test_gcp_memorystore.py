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
def populated_memorystore_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Memorystore SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/memorystore_skus.json").open() as f:
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
# MS-1: Validation Tests
# ==========================================


def test_redis_instance_valid_basic_tier() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-1",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5,
                    "tier": "BASIC",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_redis_instance_valid_standard_ha_tier() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-2",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 10,
                    "tier": "STANDARD_HA",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_redis_instance_missing_memory_size_flagged_as_error() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-3",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "BASIC",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    assert any("memory_size_gb" in e for e in result["errors"])


def test_redis_instance_tier_defaults_to_basic_with_assumption() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-4",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].attributes["tier"] == "BASIC"
    assert any("Defaulted tier to BASIC" in a for a in normalized.resources[0].assumptions)


def test_redis_instance_runtime_defaults_to_730h() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-5",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].usage["runtime_hours_per_month"] == 730


def test_memorystore_instance_valid_standalone() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "valkey-1",
                "service": "memorystore",
                "kind": "memorystore_instance",
                "region": "us-central1",
                "attributes": {
                    "node_type": "SHARED_CORE_NANO",
                    "mode": "STANDALONE",
                    "shard_count": 1,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_memorystore_instance_valid_cluster_mode() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "valkey-2",
                "service": "memorystore",
                "kind": "memorystore_instance",
                "region": "us-central1",
                "attributes": {
                    "node_type": "STANDARD_SMALL",
                    "mode": "CLUSTER",
                    "shard_count": 3,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_memorystore_instance_shard_count_defaults_to_1() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "valkey-3",
                "service": "memorystore",
                "kind": "memorystore_instance",
                "region": "us-central1",
                "attributes": {
                    "node_type": "STANDARD_SMALL",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].attributes["shard_count"] == 1
    assert any("Defaulted shard_count to 1" in a for a in normalized.resources[0].assumptions)


def test_memorystore_instance_unknown_node_type_flagged_as_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "valkey-4",
                "service": "memorystore",
                "kind": "memorystore_instance",
                "region": "us-central1",
                "attributes": {
                    "node_type": "INVALID_NODE_TYPE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("node_type" in w or "unrecognized" in w for w in result["warnings"])


def test_memorystore_instance_runtime_defaults_to_730h() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "valkey-5",
                "service": "memorystore",
                "kind": "memorystore_instance",
                "region": "us-central1",
                "attributes": {
                    "node_type": "SHARED_CORE_NANO",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].usage["runtime_hours_per_month"] == 730


# ==========================================
# MS-2: SKU Mapping Tests
# ==========================================


def test_redis_basic_maps_to_basic_capacity_sku(populated_memorystore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="redis-basic",
        service="memorystore",
        kind="redis_instance",
        region="us-central1",
        attributes={"tier": "BASIC", "memory_size_gb": 5.0},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_memorystore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-REDIS-BASIC-CAPACITY"
    assert mappings[0]["qty"] == 5.0 * 730


def test_redis_standard_ha_maps_to_ha_capacity_sku(populated_memorystore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="redis-ha",
        service="memorystore",
        kind="redis_instance",
        region="us-central1",
        attributes={"tier": "STANDARD_HA", "memory_size_gb": 10.0},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_memorystore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-REDIS-STANDARD-CAPACITY"
    assert mappings[0]["qty"] == 10.0 * 730


def test_redis_compute_qty_is_memory_gb_times_hours(populated_memorystore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="redis-qty",
        service="memorystore",
        kind="redis_instance",
        region="us-central1",
        attributes={"tier": "BASIC", "memory_size_gb": 4.0},
        usage={"runtime_hours_per_month": 100},
    )
    mapper = GcpSkuMapper(populated_memorystore_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert mappings[0]["qty"] == 4.0 * 100


def test_memorystore_standalone_maps_to_capacity_sku(populated_memorystore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="valkey-standalone",
        service="memorystore",
        kind="memorystore_instance",
        region="us-central1",
        attributes={"node_type": "STANDARD_SMALL", "shard_count": 1, "mode": "STANDALONE"},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_memorystore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-VALKEY-CAPACITY"
    # STANDARD_SMALL = 5 GB. shard_count = 1. qty = 5 * 1 * 730 = 3650
    assert mappings[0]["qty"] == 3650.0


def test_memorystore_cluster_qty_accounts_for_all_shards(populated_memorystore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="valkey-cluster",
        service="memorystore",
        kind="memorystore_instance",
        region="us-central1",
        attributes={"node_type": "SHARED_CORE_NANO", "shard_count": 3, "mode": "CLUSTER"},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_memorystore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    # SHARED_CORE_NANO = 1.0 GB. shard_count = 3. qty = 1.0 * 3 * 730 = 2190
    assert mappings[0]["qty"] == 2190.0


def test_memorystore_unknown_node_type_reported_unpriced(populated_memorystore_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="valkey-unknown",
        service="memorystore",
        kind="memorystore_instance",
        region="us-central1",
        attributes={"node_type": "UNKNOWN_SIZE", "shard_count": 1, "mode": "STANDALONE"},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_memorystore_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 0
    assert len(unpriced) > 0
    assert any("Unknown node_type" in u["reason"] for u in unpriced)


# ==========================================
# MS-3: Cost Calculation Tests
# ==========================================


def test_memorystore_cost_cases(populated_memorystore_db: str) -> None:
    with Path("tests/fixtures/memorystore_cost_cases.json").open() as f:
        cases = json.load(f)

    for case in cases:
        if case["kind"] == "redis_instance":
            res = Resource(
                provider="gcp",
                resource_id="redis-test",
                service="memorystore",
                kind="redis_instance",
                region=case["region"],
                attributes={
                    "tier": case["tier"],
                    "memory_size_gb": case["memory_size_gb"],
                },
                usage={
                    "runtime_hours_per_month": case["runtime_hours"],
                },
            )
        else:
            res = Resource(
                provider="gcp",
                resource_id="valkey-test",
                service="memorystore",
                kind="memorystore_instance",
                region=case["region"],
                attributes={
                    "node_type": case["node_type"],
                    "shard_count": case["shard_count"],
                    "mode": "CLUSTER",
                },
                usage={
                    "runtime_hours_per_month": case["runtime_hours"],
                },
            )

        model = ResourceModel(resources=[res])
        est = estimate_infrastructure(populated_memorystore_db, model)

        assert len(est.unpriced) == 0
        assert len(est.line_items) == 1
        assert pytest.approx(est.monthly_total, abs=1e-4) == case["expected_total"]


# ==========================================
# MS-4: End-to-End Estimation Tests
# ==========================================


def test_estimate_redis_basic_golden_fixture(populated_memorystore_db: str) -> None:
    data = {
        "resources": [
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
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_memorystore_db, model)

    with Path("tests/fixtures/redis_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_memorystore_standalone_golden_fixture(populated_memorystore_db: str) -> None:
    data = {
        "resources": [
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
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_memorystore_db, model)

    with Path("tests/fixtures/memorystore_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]


def test_estimate_redis_combined_with_gce_instance(populated_memorystore_db: str) -> None:
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
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_memorystore_db, model)
    # GCE CPU is 138.7. GCE RAM is 0.1008. Total GCE is 138.8008
    # Redis Basic cost is 49.275
    # The expected total cost is 188.0758
    assert pytest.approx(est.monthly_total, abs=1e-4) == 188.0758
    assert len(est.line_items) == 3


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_memorystore_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-1",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_memorystore_db, model)
    assert est.disclaimer != ""
    assert "list price only" in est.disclaimer.lower()
    assert est.pricing_snapshot == "2026-06-10T12:00:00Z"
