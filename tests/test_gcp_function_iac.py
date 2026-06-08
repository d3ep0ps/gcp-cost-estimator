# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_parse_cloudfunctions_function_1st_gen_extracts_memory_and_trigger() -> None:
    """Verify HCL parser extracts memory_mb and region for 1st-gen Cloud Functions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_cloudfunctions_function.example"
    )
    assert res.provider == "gcp"
    assert res.service == "functions"
    assert res.kind == "cloud_function"
    assert res.region == "us-central1"
    assert res.attributes["available_memory_mb"] == 256
    assert res.attributes["generation"] == "1st_gen"


def test_parse_cloudfunctions2_function_extracts_service_config() -> None:
    """Verify HCL parser extracts service_config parameters for 2nd-gen Cloud Functions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_cloudfunctions2_function.example"
    )
    assert res.provider == "gcp"
    assert res.service == "functions"
    assert res.kind == "cloud_function"
    assert res.region == "us-central1"
    assert res.attributes["available_memory"] == "512Mi"
    assert res.attributes["available_cpu"] == "1"
    assert res.attributes["min_instance_count"] == 1
    assert res.attributes["generation"] == "2nd_gen"


def test_parse_cloud_function_unresolved_runtime_variable_flagged() -> None:
    """Verify that unresolved variables in memory limits are flagged in assumptions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_cloudfunctions_function.unresolved"
    )
    assert any("unresolved attribute" in a.lower() for a in res.assumptions)


def test_plan_json_resolves_cloud_functions_resources() -> None:
    """Verify plan JSON parser extracts both generations of Cloud Functions."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/function_plan.json")

    f1 = next(
        r for r in model.resources if r.resource_id == "google_cloudfunctions_function.example"
    )
    assert f1.provider == "gcp"
    assert f1.service == "functions"
    assert f1.kind == "cloud_function"
    assert f1.region == "us-central1"
    assert f1.attributes["available_memory_mb"] == 256
    assert f1.attributes["generation"] == "1st_gen"

    f2 = next(
        r for r in model.resources if r.resource_id == "google_cloudfunctions2_function.example"
    )
    assert f2.provider == "gcp"
    assert f2.service == "functions"
    assert f2.kind == "cloud_function"
    assert f2.region == "us-central1"
    assert f2.attributes["available_memory"] == "512Mi"
    assert f2.attributes["available_cpu"] == "1"
    assert f2.attributes["min_instance_count"] == 1
    assert f2.attributes["generation"] == "2nd_gen"
