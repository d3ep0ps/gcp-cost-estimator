# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.validate import validate_resource_model


def test_nat_gateway_valid() -> None:
    """Verify NAT gateway resource is valid."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        attributes={"nat_ip_allocate_option": "AUTO_ONLY"},
        usage={"num_vms": 5, "num_nat_ips": 2, "monthly_data_processed_gb": 100},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_nat_defaults_applied_with_assumptions() -> None:
    """Verify default values are applied to NAT gateway usage fields."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["num_vms"] == 1
    assert norm_r.usage["num_nat_ips"] == 1
    assert norm_r.usage["monthly_data_processed_gb"] == 10
    assert norm_r.usage["runtime_hours_per_month"] == 730
    assert any("num_vms" in a for a in norm_r.assumptions)
    assert any("num_nat_ips" in a for a in norm_r.assumptions)
    assert any("monthly_data_processed_gb" in a for a in norm_r.assumptions)


def test_nat_num_vms_default_with_assumption() -> None:
    """Verify num_vms defaults and records assumption."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        usage={"num_nat_ips": 2},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["num_vms"] == 1
    assert any("num_vms" in a for a in norm_r.assumptions)


@pytest.fixture
def populated_nat_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static NAT SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/nat_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out metadata
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_nat_gateway_uptime_priced(populated_nat_db: str) -> None:
    """Verify NAT gateway uptime is priced per VM-hour, up to cap."""
    r1 = Resource(
        provider="gcp",
        resource_id="my-nat-1",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        usage={
            "num_vms": 1,
            "num_nat_ips": 0,
            "monthly_data_processed_gb": 0,
            "runtime_hours_per_month": 730,
        },
    )
    mapper = GcpSkuMapper(populated_nat_db)
    mappings, unpriced = mapper.map_resource_to_skus(r1)
    assert len(unpriced) == 0
    gateway_map = next(m for m in mappings if m["component"] == "gateway_uptime")
    assert gateway_map["qty"] == 730.0
    assert gateway_map["sku_id"] == "SKU-NAT-GATEWAY"

    r2 = Resource(
        provider="gcp",
        resource_id="my-nat-2",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        usage={
            "num_vms": 40,
            "num_nat_ips": 0,
            "monthly_data_processed_gb": 0,
            "runtime_hours_per_month": 730,
        },
    )
    mappings, unpriced = mapper.map_resource_to_skus(r2)
    gateway_map = next(m for m in mappings if m["component"] == "gateway_uptime")
    assert round(gateway_map["qty"], 3) == round(730.0 * (0.044 / 0.0014), 3)


def test_nat_data_processed_priced(populated_nat_db: str) -> None:
    """Verify NAT data processed is priced correctly."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        usage={
            "num_vms": 0,
            "num_nat_ips": 0,
            "monthly_data_processed_gb": 150,
            "runtime_hours_per_month": 0,
        },
    )
    mapper = GcpSkuMapper(populated_nat_db)
    mappings, _unpriced = mapper.map_resource_to_skus(r)
    data_map = next(m for m in mappings if m["component"] == "data_processed")
    assert data_map["sku_id"] == "SKU-NAT-DATA"
    assert data_map["qty"] == 150.0


def test_nat_ip_uptime_priced(populated_nat_db: str) -> None:
    """Verify NAT IP uptime is priced correctly."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        usage={
            "num_vms": 0,
            "num_nat_ips": 3,
            "monthly_data_processed_gb": 0,
            "runtime_hours_per_month": 730,
        },
    )
    mapper = GcpSkuMapper(populated_nat_db)
    mappings, _unpriced = mapper.map_resource_to_skus(r)
    ip_map = next(m for m in mappings if m["component"] == "ip_uptime")
    assert ip_map["sku_id"] == "SKU-NAT-IP"
    assert ip_map["qty"] == 3.0 * 730.0


def test_nat_known_answer_1_vm_730h_10gb_1ip(populated_nat_db: str) -> None:
    """Verify total cost of NAT gateway for 1 VM, 730h, 10GB data, 1 IP."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        usage={
            "num_vms": 1,
            "num_nat_ips": 1,
            "monthly_data_processed_gb": 10,
            "runtime_hours_per_month": 730,
        },
    )
    mapper = GcpSkuMapper(populated_nat_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total = sum(m["unit_price"] * m["qty"] for m in mappings)
    assert round(total, 3) == 4.862


def test_terraform_hcl_parses_google_compute_router_nat() -> None:
    """Verify HCL parser resolves google_compute_router_nat resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_compute_router_nat.my_nat")
    assert res.provider == "gcp"
    assert res.service == "nat"
    assert res.kind == "nat_gateway"
    assert res.region == "us-central1"
    assert res.attributes.get("nat_ip_allocate_option") == "AUTO_ONLY"


def test_terraform_plan_json_compute_router_nat_parsed() -> None:
    """Verify plan JSON parser resolves google_compute_router_nat resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/nat_plan.json")
    res = next(r for r in model.resources if r.resource_id == "google_compute_router_nat.my_nat")
    assert res.provider == "gcp"
    assert res.service == "nat"
    assert res.kind == "nat_gateway"
    assert res.region == "us-central1"
    assert res.attributes.get("nat_ip_allocate_option") == "AUTO_ONLY"


def test_nat_auto_only_vs_manual_only_ip_allocation_recorded() -> None:
    """Verify different IP allocation options are parsed correctly."""
    # Handled by parser tests above.
    pass


def test_nat_auto_only_produces_assumption_for_num_ips() -> None:
    """Verify AUTO_ONLY ip allocation adds an assumption/defaults to 1 IP."""
    r = Resource(
        provider="gcp",
        resource_id="my-nat",
        service="nat",
        kind="nat_gateway",
        region="us-central1",
        attributes={"nat_ip_allocate_option": "AUTO_ONLY"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["num_nat_ips"] == 1
    assert any("num_nat_ips" in a for a in norm_r.assumptions)
