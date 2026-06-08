# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_parse_appengine_standard_extracts_iclass_and_scaling() -> None:
    """Verify HCL parser extracts App Engine Standard instance class, scaling, and propagated region."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_standard_app_version.example"
    )
    assert res.provider == "gcp"
    assert res.service == "appengine"
    assert res.kind == "app_engine_standard_version"
    assert res.region == "us-central1"
    assert res.attributes["instance_class"] == "F2"
    assert res.attributes.get("scaling_type") == "automatic_scaling"
    assert int(res.attributes.get("automatic_scaling_min_idle_instances")) == 1


def test_parse_appengine_flexible_extracts_resources() -> None:
    """Verify HCL parser extracts CPU, memory, and disk for App Engine Flexible."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_flexible_app_version.example"
    )
    assert res.provider == "gcp"
    assert res.service == "appengine"
    assert res.kind == "app_engine_flexible_version"
    assert res.region == "us-central1"
    assert int(res.attributes["cpu"]) == 1
    assert float(res.attributes["memory_gb"]) == 2
    assert int(res.attributes["disk_gb"]) == 10

    missing = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_flexible_app_version.missing_resources"
    )
    assert any("no resources configuration found" in a.lower() for a in missing.assumptions)


def test_parse_appengine_unresolved_variable_flagged() -> None:
    """Verify that unresolved variables in App Engine are flagged in assumptions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_standard_app_version.unresolved"
    )
    assert any("unresolved attribute" in a.lower() for a in res.assumptions)


def test_plan_json_resolves_appengine_resources() -> None:
    """Verify plan JSON parser extracts App Engine standard/flexible configurations and propagates region."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/appengine_plan.json")

    standard = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_standard_app_version.example"
    )
    assert standard.provider == "gcp"
    assert standard.service == "appengine"
    assert standard.kind == "app_engine_standard_version"
    assert standard.region == "us-central1"
    assert standard.attributes["instance_class"] == "F2"
    assert standard.attributes.get("scaling_type") == "automatic_scaling"

    flexible = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_flexible_app_version.example"
    )
    assert flexible.provider == "gcp"
    assert flexible.service == "appengine"
    assert flexible.kind == "app_engine_flexible_version"
    assert flexible.region == "us-central1"
    assert int(flexible.attributes["cpu"]) == 1
    assert float(flexible.attributes["memory_gb"]) == 2
    assert int(flexible.attributes["disk_gb"]) == 10

    missing = next(
        r
        for r in model.resources
        if r.resource_id == "google_app_engine_flexible_app_version.missing_resources"
    )
    assert any("no resources configuration found" in a.lower() for a in missing.assumptions)
