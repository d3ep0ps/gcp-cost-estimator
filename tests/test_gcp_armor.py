# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.validate import validate_resource_model


def test_compute_security_policy_valid() -> None:
    """Verify compute security policy resource is valid."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes={"rule_count": 5},
        usage={"monthly_requests": 2000000},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_armor_default_request_volume_applied_with_assumption() -> None:
    """Verify default monthly request volume is applied to security policy."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["monthly_requests"] == 1000000
    assert any("monthly_requests" in a for a in norm_r.assumptions)


@pytest.fixture
def populated_armor_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Armor SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/armor_skus.json").open() as f:
        mock_skus = json.load(f)

    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_armor_policy_cost_priced(populated_armor_db: str) -> None:
    """Verify policy cost is priced ($5/policy/month)."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes={"rule_count": 0},
        usage={"monthly_requests": 0},
    )
    mapper = GcpSkuMapper(populated_armor_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    policy_map = next(m for m in mappings if m["component"] == "security_policy")
    assert policy_map["sku_id"] == "SKU-ARMOR-POLICY"
    assert policy_map["qty"] == 1.0


def test_armor_rules_cost_priced(populated_armor_db: str) -> None:
    """Verify rules cost is priced ($1/rule/month)."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes={"rule_count": 3},
        usage={"monthly_requests": 0},
    )
    mapper = GcpSkuMapper(populated_armor_db)
    mappings, _unpriced = mapper.map_resource_to_skus(r)
    rule_map = next(m for m in mappings if m["component"] == "security_rules")
    assert rule_map["sku_id"] == "SKU-ARMOR-RULE"
    assert rule_map["qty"] == 3.0


def test_armor_requests_cost_priced(populated_armor_db: str) -> None:
    """Verify requests cost is priced ($0.75/million requests)."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes={"rule_count": 0},
        usage={"monthly_requests": 5000000},
    )
    mapper = GcpSkuMapper(populated_armor_db)
    mappings, _unpriced = mapper.map_resource_to_skus(r)
    req_map = next(m for m in mappings if m["component"] == "requests")
    assert req_map["sku_id"] == "SKU-ARMOR-REQUESTS"
    assert req_map["qty"] == 5.0


def test_armor_zero_rules_returns_policy_cost_only(populated_armor_db: str) -> None:
    """Verify policy with 0 rules only returns policy cost."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes={"rule_count": 0},
        usage={"monthly_requests": 0},
    )
    mapper = GcpSkuMapper(populated_armor_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["component"] == "security_policy"


def test_armor_known_answer_1_policy_3_rules_1m_requests(populated_armor_db: str) -> None:
    """Verify total cost for 1 policy, 3 rules, and 1M requests."""
    r = Resource(
        provider="gcp",
        resource_id="my-policy",
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes={"rule_count": 3},
        usage={"monthly_requests": 1000000},
    )
    mapper = GcpSkuMapper(populated_armor_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total = sum(m["unit_price"] * m["qty"] for m in mappings)
    assert round(total, 2) == 8.75


def test_terraform_hcl_parses_google_compute_security_policy() -> None:
    """Verify HCL parser resolves google_compute_security_policy resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_security_policy.my_policy"
    )
    assert res.provider == "gcp"
    assert res.service == "armor"
    assert res.kind == "compute_security_policy"
    assert res.region == "global" or res.region is None


def test_terraform_hcl_rule_count_extracted_correctly() -> None:
    """Verify HCL parser extracts the correct rule count from security policy."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_security_policy.my_policy"
    )
    assert res.attributes.get("rule_count") == 2


def test_terraform_plan_json_security_policy_parsed() -> None:
    """Verify plan JSON parser resolves google_compute_security_policy resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/armor_plan.json")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_security_policy.my_policy"
    )
    assert res.provider == "gcp"
    assert res.service == "armor"
    assert res.kind == "compute_security_policy"
    assert res.attributes.get("rule_count") == 2
