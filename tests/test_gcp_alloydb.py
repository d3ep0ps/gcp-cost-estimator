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

# ==========================================
# AD-1: Validation Tests
# ==========================================


def test_alloydb_cluster_valid_minimal() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-cluster-1",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
                "attributes": {},
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_alloydb_cluster_storage_defaults_to_100gb_with_assumption() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-cluster-1",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    norm_res = result["normalized_model"].resources[0]
    assert norm_res.usage["storage_gb"] == 100
    assert any("Defaulted storage_gb to 100" in a for a in norm_res.assumptions)


def test_alloydb_cluster_backup_defaults_to_disabled_with_assumption() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-cluster-1",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    norm_res = result["normalized_model"].resources[0]
    assert norm_res.usage["backup_enabled"] is False


def test_alloydb_instance_valid_primary() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-1",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRIMARY",
                    "cpu_count": 4,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_alloydb_instance_valid_read_pool() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-read-pool",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "READ_POOL",
                    "cpu_count": 8,
                    "node_count": 2,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_alloydb_instance_missing_cpu_count_flagged_as_error() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-err",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRIMARY",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("missing cpu_count" in e.lower() for e in result["errors"])


def test_alloydb_instance_unknown_cpu_count_flagged_as_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-warn",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRIMARY",
                    "cpu_count": 5,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("unsupported vcpu count" in w.lower() for w in result["warnings"])


def test_alloydb_instance_read_pool_node_count_defaults_to_1() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-read-pool",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "READ_POOL",
                    "cpu_count": 8,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    norm_res = result["normalized_model"].resources[0]
    assert norm_res.attributes["node_count"] == 1


def test_alloydb_instance_primary_password_redacted() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-cluster-1",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
                "attributes": {"initial_user": {"password": "super-secret-password"}},
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    # The password redaction actually happens at parsing time (IaC),
    # but we also ensure it's not present or is redacted in the model/validation.
    assert result["valid"] is True
    # If the password attribute got into the attributes, it must be removed or not secret
    # Let's check how password is handled in validate/normalize
    norm_res = result["normalized_model"].resources[0]
    initial_user = norm_res.attributes.get("initial_user", {})
    if initial_user:
        assert "password" not in initial_user or initial_user["password"] == "[REDACTED]"


def test_alloydb_instance_runtime_defaults_to_730h() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-instance-1",
                "service": "alloydb",
                "kind": "alloydb_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRIMARY",
                    "cpu_count": 4,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    norm_res = result["normalized_model"].resources[0]
    assert norm_res.usage["runtime_hours_per_month"] == 730


# ==========================================
# AD-2: Resolver Tests
# ==========================================


def test_resolve_alloydb_instance_specs() -> None:
    from gcp_cost_estimator.core.pricing.gcp import resolve_alloydb_instance_specs

    assert resolve_alloydb_instance_specs(2) == (2, 16.0)
    assert resolve_alloydb_instance_specs(4) == (4, 32.0)
    assert resolve_alloydb_instance_specs(8) == (8, 64.0)
    assert resolve_alloydb_instance_specs(16) == (16, 128.0)
    assert resolve_alloydb_instance_specs(32) == (32, 256.0)
    assert resolve_alloydb_instance_specs(64) == (64, 512.0)
    assert resolve_alloydb_instance_specs(96) == (96, 768.0)
    assert resolve_alloydb_instance_specs(128) == (128, 864.0)
    assert resolve_alloydb_instance_specs(5) == (0, 0.0)


@pytest.fixture
def populated_alloydb_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static AlloyDB SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/alloydb_skus.json").open() as f:
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
# AD-3: SKU Mapping Tests
# ==========================================


def test_alloydb_primary_instance_maps_to_vcpu_sku(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-primary",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRIMARY",
            "cpu_count": 4,
        },
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 2
    vcpu = next(m for m in mappings if m["component"] == "compute_vcpu")
    assert vcpu["sku_id"] == "SKU-ALLOYDB-VCPU"
    assert vcpu["qty"] == 4 * 730


def test_alloydb_primary_instance_maps_to_ram_sku(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-primary",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRIMARY",
            "cpu_count": 4,
        },
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    ram = next(m for m in mappings if m["component"] == "compute_ram")
    assert ram["sku_id"] == "SKU-ALLOYDB-RAM"
    assert ram["qty"] == 32 * 730


def test_alloydb_read_pool_qty_multiplied_by_node_count(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-read-pool",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "READ_POOL",
            "cpu_count": 8,
            "node_count": 2,
        },
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    vcpu = next(m for m in mappings if m["component"] == "compute_vcpu")
    assert vcpu["qty"] == 8 * 2 * 730
    ram = next(m for m in mappings if m["component"] == "compute_ram")
    assert ram["qty"] == 64 * 2 * 730


def test_alloydb_cluster_storage_sku_emitted(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-cluster",
        service="alloydb",
        kind="alloydb_cluster",
        region="us-central1",
        attributes={},
        usage={"storage_gb": 100},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    storage = mappings[0]
    assert storage["sku_id"] == "SKU-ALLOYDB-STORAGE"
    assert storage["qty"] == 100.0


def test_alloydb_cluster_backup_sku_emitted_when_enabled(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-cluster",
        service="alloydb",
        kind="alloydb_cluster",
        region="us-central1",
        attributes={},
        usage={"storage_gb": 100, "backup_enabled": True},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 2
    backup = next(m for m in mappings if m["component"] == "backup")
    assert backup["sku_id"] == "SKU-ALLOYDB-BACKUP"
    assert backup["qty"] == 100.0


def test_alloydb_cluster_backup_not_emitted_when_disabled(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-cluster",
        service="alloydb",
        kind="alloydb_cluster",
        region="us-central1",
        attributes={},
        usage={"storage_gb": 100, "backup_enabled": False},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert not any(m["component"] == "backup" for m in mappings)


def test_alloydb_unresolvable_cpu_count_reported_unpriced(populated_alloydb_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="alloydb-instance",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRIMARY",
            "cpu_count": 5,
        },
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_alloydb_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 0
    assert len(unpriced) > 0
    assert "cpu_count" in unpriced[0]["reason"]


# ==========================================
# AD-4: Cost Calculation Tests
# ==========================================


def test_alloydb_cost_cases(populated_alloydb_db: str) -> None:
    with Path("tests/fixtures/alloydb_cost_cases.json").open() as f:
        cases = json.load(f)

    for case in cases:
        res_list = []
        # Create cluster resource
        cluster_res = Resource(
            provider="gcp",
            resource_id="alloydb-cluster-test",
            service="alloydb",
            kind="alloydb_cluster",
            region=case["region"],
            attributes={},
            usage={
                "storage_gb": case["storage_gb"],
                "backup_enabled": case["backup_enabled"],
            },
        )
        res_list.append(cluster_res)

        # Create instance resource
        instance_res = Resource(
            provider="gcp",
            resource_id="alloydb-instance-test",
            service="alloydb",
            kind="alloydb_instance",
            region=case["region"],
            attributes={
                "instance_type": case["instance_type"],
                "cpu_count": case["cpu_count"],
                "node_count": case["node_count"],
            },
            usage={
                "runtime_hours_per_month": case["runtime_hours"],
            },
        )
        res_list.append(instance_res)

        model = ResourceModel(resources=res_list)
        est = estimate_infrastructure(populated_alloydb_db, model)

        assert len(est.unpriced) == 0
        assert pytest.approx(est.monthly_total, abs=1e-4) == case["expected_total"]


# ==========================================
# AD-5: End-to-End Estimation Tests
# ==========================================


def test_estimate_alloydb_primary_only_golden_fixture(populated_alloydb_db: str) -> None:
    data = {
        "resources": [
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
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_alloydb_db, model)

    with Path("tests/fixtures/alloydb_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["sku_id"] == item.sku_id)
        assert golden_item["component"] == item.component
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost
