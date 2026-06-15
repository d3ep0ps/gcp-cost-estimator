# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path
import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper


def test_compute_address_external_valid() -> None:
    """Verify EXTERNAL compute address is valid."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "EXTERNAL"},
        usage={"in_use": True, "on_spot_vm": False, "on_forwarding_rule": False},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_compute_address_forwarding_rule_returns_no_charge() -> None:
    """Verify forwarding rule compute address returns no charge (cost 0)."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        usage={"on_forwarding_rule": True},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["on_forwarding_rule"] is True


def test_compute_address_unused_default_is_in_use() -> None:
    """Verify in_use defaults to True."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["in_use"] is True
    assert any("in_use" in a for a in norm_r.assumptions)


def test_compute_address_on_spot_vm_recorded() -> None:
    """Verify on_spot_vm attribute is normalized correctly."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        usage={"on_spot_vm": True},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["on_spot_vm"] is True


@pytest.fixture
def populated_vpc_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static VPC SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/vpc_skus.json").open() as f:
        mock_skus = json.load(f)

    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_vpc_ip_unused_priced_at_reserved_rate(populated_vpc_db: str) -> None:
    """Verify unused IP is priced at reserved rate ($0.01/hr)."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "EXTERNAL"},
        usage={"in_use": False, "runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vpc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    ip_map = next(m for m in mappings if m["component"] == "static_ip")
    assert ip_map["sku_id"] == "SKU-VPC-STATIC-IP-UNUSED"
    assert ip_map["qty"] == 730.0


def test_vpc_ip_in_use_standard_vm_rate(populated_vpc_db: str) -> None:
    """Verify IP in use on standard VM is priced at standard in-use rate ($0.005/hr)."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "EXTERNAL"},
        usage={"in_use": True, "on_spot_vm": False, "on_forwarding_rule": False, "runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vpc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    ip_map = next(m for m in mappings if m["component"] == "static_ip")
    assert ip_map["sku_id"] == "SKU-VPC-STATIC-IP-INUSE"
    assert ip_map["qty"] == 730.0


def test_vpc_ip_in_use_spot_vm_rate(populated_vpc_db: str) -> None:
    """Verify IP in use on Spot VM is priced at Spot rate ($0.0025/hr)."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "EXTERNAL"},
        usage={"in_use": True, "on_spot_vm": True, "on_forwarding_rule": False, "runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vpc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    ip_map = next(m for m in mappings if m["component"] == "static_ip")
    assert ip_map["sku_id"] == "SKU-VPC-STATIC-IP-SPOT"
    assert ip_map["qty"] == 730.0


def test_vpc_ip_on_forwarding_rule_zero_cost(populated_vpc_db: str) -> None:
    """Verify IP attached to a forwarding rule has no charge (not billed)."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "EXTERNAL"},
        usage={"in_use": True, "on_forwarding_rule": True, "runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vpc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    assert len(mappings) == 0


def test_compute_address_internal_returns_unpriced_execution(populated_vpc_db: str) -> None:
    """Verify internal IP address goes to unpriced."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "INTERNAL"},
    )
    mapper = GcpSkuMapper(populated_vpc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "Internal IP addresses are free" in unpriced[0]["reason"]


def test_vpc_ip_known_answer_730h_in_use_standard(populated_vpc_db: str) -> None:
    """Verify total cost of static IP for 730h standard in-use."""
    r = Resource(
        provider="gcp",
        resource_id="my-ip",
        service="vpc",
        kind="compute_address",
        region="us-central1",
        attributes={"address_type": "EXTERNAL"},
        usage={"in_use": True, "on_spot_vm": False, "on_forwarding_rule": False, "runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vpc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total = sum(m["unit_price"] * m["qty"] for m in mappings)
    assert round(total, 2) == 3.65


def test_terraform_hcl_parses_google_compute_address_external() -> None:
    """Verify HCL parser resolves google_compute_address external resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_compute_address.my_static_ip")
    assert res.provider == "gcp"
    assert res.service == "vpc"
    assert res.kind == "compute_address"
    assert res.region == "us-central1"
    assert res.attributes.get("address_type") == "EXTERNAL"


def test_terraform_plan_json_compute_address_parsed() -> None:
    """Verify plan JSON parser resolves google_compute_address resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/vpc_plan.json")
    res = next(r for r in model.resources if r.resource_id == "google_compute_address.my_static_ip")
    assert res.provider == "gcp"
    assert res.service == "vpc"
    assert res.kind == "compute_address"
    assert res.region == "us-central1"
    assert res.attributes.get("address_type") == "EXTERNAL"
