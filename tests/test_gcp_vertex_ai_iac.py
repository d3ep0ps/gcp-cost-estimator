# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_hcl_parses_google_vertex_ai_endpoint() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    # Dedicated endpoint
    dedicated = next(
        r for r in model.resources if r.resource_id == "google_vertex_ai_endpoint.dedicated"
    )
    assert dedicated.provider == "gcp"
    assert dedicated.service == "vertex"
    assert dedicated.kind == "google_vertex_ai_endpoint"
    assert dedicated.region == "us-central1"
    assert dedicated.attributes["dedicated_endpoint_enabled"] is True

    # Shared endpoint
    shared = next(r for r in model.resources if r.resource_id == "google_vertex_ai_endpoint.shared")
    assert shared.provider == "gcp"
    assert shared.service == "vertex"
    assert shared.kind == "google_vertex_ai_endpoint"
    assert shared.region == "us-central1"
    assert shared.attributes.get("dedicated_endpoint_enabled", False) is False


def test_plan_json_resolves_google_vertex_ai_endpoint() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/vertex_ai_plan.json")

    # Dedicated endpoint
    dedicated = next(
        r for r in model.resources if r.resource_id == "google_vertex_ai_endpoint.dedicated"
    )
    assert dedicated.provider == "gcp"
    assert dedicated.service == "vertex"
    assert dedicated.kind == "google_vertex_ai_endpoint"
    assert dedicated.region == "us-central1"
    assert dedicated.attributes["dedicated_endpoint_enabled"] is True

    # Shared endpoint
    shared = next(r for r in model.resources if r.resource_id == "google_vertex_ai_endpoint.shared")
    assert shared.provider == "gcp"
    assert shared.service == "vertex"
    assert shared.kind == "google_vertex_ai_endpoint"
    assert shared.region == "us-central1"
    assert shared.attributes.get("dedicated_endpoint_enabled", False) is False
