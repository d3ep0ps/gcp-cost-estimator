# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.validate import validate_resource_model


def test_dns_managed_zone_valid_public() -> None:
    """Verify public managed zone is valid."""
    r = Resource(
        provider="gcp",
        resource_id="public-zone",
        service="dns",
        kind="dns_managed_zone",
        region="global",
        attributes={"visibility": "public"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_dns_managed_zone_valid_private() -> None:
    """Verify private managed zone is valid."""
    r = Resource(
        provider="gcp",
        resource_id="private-zone",
        service="dns",
        kind="dns_managed_zone",
        region="global",
        attributes={"visibility": "private"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_dns_monthly_queries_default_applied() -> None:
    """Verify monthly queries default is applied."""
    r = Resource(
        provider="gcp",
        resource_id="zone-1",
        service="dns",
        kind="dns_managed_zone",
        region="global",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["monthly_queries"] == 1000000
    assert any("monthly_queries" in a for a in norm_r.assumptions)


@pytest.fixture
def populated_dns_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static DNS SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/dns_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out metadata
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_dns_zone_cost_first_25_zones_rate(populated_dns_db: str) -> None:
    """Verify DNS zone cost mapping."""
    r = Resource(
        provider="gcp",
        resource_id="zone-1",
        service="dns",
        kind="dns_managed_zone",
        region="global",
        usage={"monthly_queries": 0},
    )
    mapper = GcpSkuMapper(populated_dns_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    zone_map = next(m for m in mappings if m["component"] == "managed_zones")
    assert zone_map["sku_id"] == "SKU-DNS-ZONE"
    assert zone_map["qty"] == 1.0


def test_dns_query_cost_first_billion_rate(populated_dns_db: str) -> None:
    """Verify DNS queries cost mapping."""
    r = Resource(
        provider="gcp",
        resource_id="zone-1",
        service="dns",
        kind="dns_managed_zone",
        region="global",
        usage={"monthly_queries": 5000000},  # 5M queries
    )
    mapper = GcpSkuMapper(populated_dns_db)
    # We want to make sure only queries cost is verified, so zone cost is 0 by setting quantity = 0? No, standard zone quantity is 1
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    query_map = next(m for m in mappings if m["component"] == "dns_queries")
    assert query_map["sku_id"] == "SKU-DNS-QUERIES"
    # Unit is 1M requests, so 5M / 1M = 5.0
    assert query_map["qty"] == 5.0


def test_dns_known_answer_1_zone_1m_queries(populated_dns_db: str) -> None:
    """Verify DNS total cost for 1 zone and 1M queries."""
    # 1 zone = $0.20
    # 1M queries = $0.40
    # Total = $0.60
    r = Resource(
        provider="gcp",
        resource_id="zone-1",
        service="dns",
        kind="dns_managed_zone",
        region="global",
        usage={"monthly_queries": 1000000},
    )
    mapper = GcpSkuMapper(populated_dns_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total_cost = sum(m["unit_price"] * m["qty"] for m in mappings)
    assert round(total_cost, 2) == 0.60


def test_terraform_hcl_parses_google_dns_managed_zone() -> None:
    """Verify HCL parser resolves google_dns_managed_zone resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_dns_managed_zone.my_zone")
    assert res.provider == "gcp"
    assert res.service == "dns"
    assert res.kind == "dns_managed_zone"
    # DNS zones are global
    assert res.region == "global" or res.region is None
    assert res.attributes.get("visibility") == "public"


def test_terraform_plan_json_dns_managed_zone_parsed() -> None:
    """Verify plan JSON parser resolves dns_managed_zone resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/dns_plan.json")
    res = next(r for r in model.resources if r.resource_id == "google_dns_managed_zone.my_zone")
    assert res.provider == "gcp"
    assert res.service == "dns"
    assert res.kind == "dns_managed_zone"
    assert res.attributes.get("visibility") == "public"
