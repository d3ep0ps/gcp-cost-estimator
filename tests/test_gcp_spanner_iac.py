# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_hcl_parses_google_spanner_instance_processing_units() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_spanner_instance.spanner_pu")
    assert res.provider == "gcp"
    assert res.service == "spanner"
    assert res.kind == "spanner_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["processing_units"]) == 100
    assert res.attributes["edition"] == "STANDARD"


def test_hcl_parses_google_spanner_instance_num_nodes() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_spanner_instance.spanner_nodes"
    )
    assert res.provider == "gcp"
    assert res.service == "spanner"
    assert res.kind == "spanner_instance"
    assert res.region == "us-central1"  # Derived from config="nam6"
    assert int(res.attributes["num_nodes"]) == 2
    assert res.attributes["edition"] == "ENTERPRISE_PLUS"


def test_hcl_spanner_num_nodes_converted_to_processing_units() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_spanner_instance.spanner_nodes"
    )
    # Validate converts to normalized processing units
    single_model = ResourceModel(resources=[res])
    result = validate_resource_model(single_model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["processing_units"] == 2000


def test_hcl_spanner_unresolved_var_in_processing_units_flagged() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_spanner_instance.spanner_unresolved"
    )
    assert any("unresolved attribute" in a.lower() for a in res.assumptions)


def test_plan_json_resolves_google_spanner_instance() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/spanner_plan.json")

    res = next(r for r in model.resources if r.resource_id == "google_spanner_instance.spanner_pu")
    assert res.provider == "gcp"
    assert res.service == "spanner"
    assert res.kind == "spanner_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["processing_units"]) == 100
    assert res.attributes["edition"] == "STANDARD"


def test_plan_json_spanner_resolves_num_nodes() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/spanner_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_spanner_instance.spanner_nodes"
    )
    assert res.provider == "gcp"
    assert res.service == "spanner"
    assert res.kind == "spanner_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["num_nodes"]) == 2
    assert res.attributes["edition"] == "ENTERPRISE_PLUS"

    result = validate_resource_model(model)
    assert result["valid"] is True
    res_norm = next(
        r
        for r in result["normalized_model"].resources
        if r.resource_id == "google_spanner_instance.spanner_nodes"
    )
    assert res_norm.attributes["processing_units"] == 2000
