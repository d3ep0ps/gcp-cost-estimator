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
def populated_spanner_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Cloud Spanner SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/spanner_skus.json").open() as f:
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
# SP-1: Validation Tests
# ==========================================


def test_spanner_instance_valid_standard_regional() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-1",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                    "edition": "STANDARD",
                    "processing_units": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_spanner_instance_valid_enterprise_plus_multi_region() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-2",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "nam6",
                    "edition": "ENTERPRISE_PLUS",
                    "processing_units": 1000,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_spanner_num_nodes_converted_to_processing_units() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-3",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                    "num_nodes": 2,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["processing_units"] == 2000


def test_spanner_both_num_nodes_and_processing_units_is_error() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-4",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                    "num_nodes": 1,
                    "processing_units": 1000,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("both" in e or "num_nodes" in e for e in result["errors"])


def test_spanner_unknown_edition_flagged_as_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-5",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                    "edition": "INVALID_EDITION",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("edition" in w or "unrecognized" in w for w in result["warnings"])


def test_spanner_missing_config_flagged_as_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-6",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "edition": "STANDARD",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("config" in w for w in result["warnings"])


def test_spanner_processing_units_defaults_to_100_with_assumption() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-7",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["processing_units"] == 100
    assert any(
        "Defaulted processing_units to 100" in a for a in normalized.resources[0].assumptions
    )


def test_spanner_storage_defaults_to_zero_with_assumption() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-8",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].usage.get("storage_gb") == 0
    assert any("storage_gb" in a for a in normalized.resources[0].assumptions)


def test_spanner_runtime_defaults_to_730h() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-9",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].usage.get("runtime_hours_per_month") == 730


def test_spanner_multi_region_config_storage_multiplier_recorded() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-10",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "nam6",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes.get("config_type") == "multi-region"
    assert any("storage multiplier" in a.lower() for a in normalized.resources[0].assumptions)


# ==========================================
# SP-2: SKU Mapping Tests
# ==========================================


def test_spanner_standard_regional_maps_to_compute_sku(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-std-reg",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-SPANNER-STD-REG-COMPUTE"
    assert mappings[0]["qty"] == 100 * 730


def test_spanner_enterprise_regional_maps_to_enterprise_compute_sku(
    populated_spanner_db: str,
) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-ent-reg",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "ENTERPRISE",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-SPANNER-ENT-REG-COMPUTE"


def test_spanner_enterprise_plus_maps_to_enterprise_plus_sku(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-entplus-mr",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "nam6",
            "config_type": "multi-region",
            "edition": "ENTERPRISE_PLUS",
            "processing_units": 1000,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-SPANNER-ENTPLUS-MR-COMPUTE"


def test_spanner_compute_qty_is_processing_units_times_hours(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-qty",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 200,
        },
        usage={"runtime_hours_per_month": 100, "storage_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert mappings[0]["qty"] == 200 * 100


def test_spanner_storage_sku_emitted_when_nonzero(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-stor",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 50},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 2
    stor_map = next(m for m in mappings if m["component"] == "storage")
    assert stor_map["sku_id"] == "SKU-SPANNER-STORAGE"
    assert stor_map["qty"] == 50


def test_spanner_storage_not_emitted_when_zero(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-no-stor",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert not any(m["component"] == "storage" for m in mappings)


def test_spanner_multi_region_storage_qty_multiplied(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-mr-stor",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "nam6",
            "config_type": "multi-region",
            "edition": "STANDARD",
            "processing_units": 1000,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 50},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    stor_map = next(m for m in mappings if m["component"] == "storage")
    # nam6 is multi-region -> multiplier is 3
    assert stor_map["qty"] == 50 * 3


def test_spanner_dual_region_storage_qty_doubled(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-dr-stor",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "nam4",
            "config_type": "dual-region",
            "edition": "STANDARD",
            "processing_units": 1000,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 50},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    stor_map = next(m for m in mappings if m["component"] == "storage")
    # nam4 is dual-region -> multiplier is 2
    assert stor_map["qty"] == 50 * 2


def test_spanner_egress_sku_emitted_when_nonzero(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-egr",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0, "monthly_egress_gb": 10},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    eg_map = next(m for m in mappings if m["component"] == "egress")
    assert eg_map["sku_id"] == "SKU-SPANNER-EGRESS"
    assert eg_map["qty"] == 10


def test_spanner_egress_not_emitted_when_zero(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-no-egr",
        service="spanner",
        kind="spanner_instance",
        region="us-central1",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0, "monthly_egress_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert not any(m["component"] == "egress" for m in mappings)


def test_spanner_unresolvable_config_reported_unpriced(populated_spanner_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="spanner-unres",
        service="spanner",
        kind="spanner_instance",
        region="us-invalid-region",
        attributes={
            "config": "regional-us-central1",
            "config_type": "regional",
            "edition": "STANDARD",
            "processing_units": 100,
        },
        usage={"runtime_hours_per_month": 730, "storage_gb": 0},
    )
    mapper = GcpSkuMapper(populated_spanner_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 0
    assert len(unpriced) > 0


# ==========================================
# SP-3: Cost Calculation Tests
# ==========================================


def test_spanner_cost_cases(populated_spanner_db: str) -> None:
    with Path("tests/fixtures/spanner_cost_cases.json").open() as f:
        cases = json.load(f)

    for case in cases:
        res = Resource(
            provider="gcp",
            resource_id="spanner-test",
            service="spanner",
            kind="spanner_instance",
            region=case["region"],
            attributes={
                "config": case["config"],
                "edition": case["edition"],
                "processing_units": case["processing_units"],
            },
            usage={
                "runtime_hours_per_month": case["runtime_hours"],
                "storage_gb": case["storage_gb"],
            },
        )
        model = ResourceModel(resources=[res])
        est = estimate_infrastructure(populated_spanner_db, model)

        assert len(est.unpriced) == 0
        comp_item = next(item for item in est.line_items if item.component == "compute")
        assert pytest.approx(comp_item.monthly_cost, abs=1e-2) == case["expected_compute_cost"]

        if case["storage_gb"] > 0:
            stor_item = next(item for item in est.line_items if item.component == "storage")
            assert pytest.approx(stor_item.monthly_cost, abs=1e-2) == case["expected_storage_cost"]

        assert pytest.approx(est.monthly_total, abs=1e-2) == case["expected_total"]


# ==========================================
# SP-4: End-to-End Estimation Tests
# ==========================================


def test_estimate_spanner_standard_regional_golden_fixture(populated_spanner_db: str) -> None:
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
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_spanner_db, model)

    with Path("tests/fixtures/spanner_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_spanner_zero_storage_no_storage_line_item(populated_spanner_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-1",
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
                    "storage_gb": 0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_spanner_db, model)
    assert len(est.line_items) == 1
    assert est.line_items[0].component == "compute"


def test_estimate_spanner_defaults_recorded_in_assumptions(populated_spanner_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-1",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_spanner_db, model)
    assert any("Defaulted processing_units to 100" in a for a in est.assumptions)
    assert any("Defaulted storage_gb to 0 GB" in a for a in est.assumptions)


def test_estimate_spanner_combined_with_gce_instance(populated_spanner_db: str) -> None:
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
                "resource_id": "spanner-1",
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
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_spanner_db, model)
    # GCE CPU is 138.7. GCE RAM is 0.1008. Total GCE is 138.8008
    # Spanner compute cost is 6.57 and storage is 3.00, totaling 9.57
    # The expected total cost is 148.3708
    assert pytest.approx(est.monthly_total, abs=1e-4) == 148.3708
    assert len(est.line_items) == 4


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_spanner_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-1",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_spanner_db, model)
    assert est.disclaimer != ""
    assert "list price only" in est.disclaimer.lower()
    assert est.pricing_snapshot == "2026-06-10T12:00:00Z"
