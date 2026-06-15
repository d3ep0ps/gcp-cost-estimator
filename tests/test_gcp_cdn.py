# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_cloud_cdn_backend_bucket_valid() -> None:
    """Verify backend bucket with cdn_policy is valid."""
    r = Resource(
        provider="gcp",
        resource_id="backend-bucket",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_cloud_cdn_backend_service_valid() -> None:
    """Verify backend service with cdn_policy is valid."""
    r = Resource(
        provider="gcp",
        resource_id="backend-service",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_cloud_cdn_defaults_applied_with_assumptions() -> None:
    """Verify default values are applied when optional usage details are omitted."""
    r = Resource(
        provider="gcp",
        resource_id="backend-bucket",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]

    assert norm_r.usage["monthly_cache_transfer_gb"] == 100
    assert norm_r.usage["monthly_cache_fill_gb"] == 10
    assert norm_r.usage["monthly_requests"] == 1_000_000
    assert norm_r.usage["https_fraction"] == 1.0

    # Ensure assumptions are registered
    assert any("monthly_cache_transfer_gb" in a for a in norm_r.assumptions)
    assert any("monthly_cache_fill_gb" in a for a in norm_r.assumptions)
    assert any("monthly_requests" in a for a in norm_r.assumptions)
    assert any("https_fraction" in a for a in norm_r.assumptions)


def test_cloud_cdn_https_fraction_out_of_range_is_error() -> None:
    """Verify that https_fraction outside [0, 1] results in a validation error."""
    r = Resource(
        provider="gcp",
        resource_id="backend-bucket",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
        usage={"https_fraction": 1.5},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is False
    assert any("https_fraction" in e for e in res["errors"])


import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_cdn_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static CDN SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/cdn_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out metadata
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_cloud_cdn_no_cdn_policy_block_returns_unpriced(populated_cdn_db: str) -> None:
    """Verify that a backend resource with no cdn_policy (cdn_enabled not True) is unpriced."""
    r = Resource(
        provider="gcp",
        resource_id="backend-bucket",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": False},
    )
    mapper = GcpSkuMapper(populated_cdn_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "no cdn_policy" in unpriced[0]["reason"].lower()


def test_cdn_cache_transfer_out_us_priced(populated_cdn_db: str) -> None:
    """Verify cache transfer out maps to correct SKU and quantity."""
    r = Resource(
        provider="gcp",
        resource_id="cdn-1",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
        usage={
            "monthly_cache_transfer_gb": 150.0,
            "monthly_cache_fill_gb": 0.0,
            "monthly_requests": 0.0,
            "https_fraction": 1.0,
        },
    )
    mapper = GcpSkuMapper(populated_cdn_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    tx_map = next(m for m in mappings if m["component"] == "cache_transfer_out")
    assert tx_map["sku_id"] == "SKU-CDN-TX-USC1"
    assert tx_map["qty"] == 150.0


def test_cdn_cache_fill_priced(populated_cdn_db: str) -> None:
    """Verify cache fill maps to correct SKU and quantity."""
    r = Resource(
        provider="gcp",
        resource_id="cdn-1",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
        usage={
            "monthly_cache_transfer_gb": 0.0,
            "monthly_cache_fill_gb": 20.0,
            "monthly_requests": 0.0,
            "https_fraction": 1.0,
        },
    )
    mapper = GcpSkuMapper(populated_cdn_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    fill_map = next(m for m in mappings if m["component"] == "cache_fill")
    assert fill_map["sku_id"] == "SKU-CDN-FILL-USC1"
    assert fill_map["qty"] == 20.0


def test_cdn_http_requests_priced(populated_cdn_db: str) -> None:
    """Verify HTTP requests pricing when https_fraction is 0.0."""
    r = Resource(
        provider="gcp",
        resource_id="cdn-1",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
        usage={
            "monthly_cache_transfer_gb": 0.0,
            "monthly_cache_fill_gb": 0.0,
            "monthly_requests": 500000.0,
            "https_fraction": 0.0,
        },
    )
    mapper = GcpSkuMapper(populated_cdn_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    req_map = next(m for m in mappings if m["component"] == "http_requests")
    assert req_map["sku_id"] == "SKU-CDN-HTTP-REQ"
    # Unit is 10k requests, so 500k / 10k = 50.0
    assert req_map["qty"] == 50.0


def test_cdn_https_requests_priced_higher_than_http(populated_cdn_db: str) -> None:
    """Verify HTTPS requests pricing when https_fraction is 1.0."""
    r = Resource(
        provider="gcp",
        resource_id="cdn-1",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
        usage={
            "monthly_cache_transfer_gb": 0.0,
            "monthly_cache_fill_gb": 0.0,
            "monthly_requests": 500000.0,
            "https_fraction": 1.0,
        },
    )
    mapper = GcpSkuMapper(populated_cdn_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    req_map = next(m for m in mappings if m["component"] == "https_requests")
    assert req_map["sku_id"] == "SKU-CDN-HTTPS-REQ"
    assert req_map["qty"] == 50.0


def test_cdn_known_answer_100gb_transfer_1m_https_requests(populated_cdn_db: str) -> None:
    """Verify CDN pricing matches hand-computed expected value."""
    # 100 GB transfer out = 100 * $0.02 = $2.00
    # 10 GB cache fill = 10 * $0.01 = $0.10
    # 1M HTTPS requests = (1,000,000 / 10,000) * $0.0090 = 100 * $0.0090 = $0.90
    # Total = $3.00
    r = Resource(
        provider="gcp",
        resource_id="cdn-1",
        service="cdn",
        kind="cloud_cdn_backend",
        region="us-central1",
        attributes={"cdn_enabled": True},
        usage={
            "monthly_cache_transfer_gb": 100.0,
            "monthly_cache_fill_gb": 10.0,
            "monthly_requests": 1000000.0,
            "https_fraction": 1.0,
        },
    )
    mapper = GcpSkuMapper(populated_cdn_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0

    total_cost = sum(m["unit_price"] * m["qty"] for m in mappings)
    assert round(total_cost, 2) == 3.00


def test_terraform_hcl_parses_backend_bucket_with_cdn_policy() -> None:
    """Verify HCL parser maps google_compute_backend_bucket with cdn_policy to cloud_cdn_backend."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_backend_bucket.cdn_bucket"
    )
    assert res.provider == "gcp"
    assert res.service == "cdn"
    assert res.kind == "cloud_cdn_backend"
    assert res.region == "us-central1"
    assert res.attributes.get("cdn_enabled") is True


def test_terraform_hcl_parses_backend_service_with_cdn_policy() -> None:
    """Verify HCL parser maps google_compute_backend_service with cdn_policy to cloud_cdn_backend."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_backend_service.cdn_service"
    )
    assert res.provider == "gcp"
    assert res.service == "cdn"
    assert res.kind == "cloud_cdn_backend"
    assert res.region == "us-central1"
    assert res.attributes.get("cdn_enabled") is True


def test_terraform_hcl_backend_without_cdn_policy_produces_unpriced() -> None:
    """Verify HCL parser does not flag cdn_enabled for backend without cdn_policy."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_backend_bucket.no_cdn"
    )
    # Should not have cdn_enabled in attributes
    assert not res.attributes.get("cdn_enabled")


def test_terraform_plan_json_cdn_backend_parsed() -> None:
    """Verify plan JSON parser resolves cloud_cdn_backend correctly."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/cdn_plan.json")
    res = next(
        r for r in model.resources if r.resource_id == "google_compute_backend_bucket.cdn_bucket"
    )
    assert res.provider == "gcp"
    assert res.service == "cdn"
    assert res.kind == "cloud_cdn_backend"
    assert res.region == "us-central1"
    assert res.attributes.get("cdn_enabled") is True
