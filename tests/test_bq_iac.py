# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_hcl_parses_google_bigquery_dataset_minimal() -> None:
    """Verify HCL parser extracts minimal bigquery dataset resource."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    r = next(
        (x for x in model.resources if x.resource_id == "google_bigquery_dataset.minimal"),
        None,
    )
    assert r is not None
    assert r.provider == "gcp"
    assert r.service == "bigquery"
    assert r.kind == "bigquery_dataset"
    assert r.region is None or r.region == ""


def test_hcl_parses_google_bigquery_dataset_with_location() -> None:
    """Verify HCL parser extracts location field from dataset resource."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    r = next(
        (x for x in model.resources if x.resource_id == "google_bigquery_dataset.with_location"),
        None,
    )
    assert r is not None
    assert r.region == "US"


def test_hcl_bigquery_table_parsed_but_no_separate_resource_emitted() -> None:
    """Verify tables do not produce separate resources, but are parsed/acknowledged."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    # There should NOT be any table resource
    resources = [
        x
        for x in model.resources
        if x.kind == "bigquery_table" or "google_bigquery_table" in x.resource_id
    ]
    assert len(resources) == 0


def test_hcl_bigquery_unresolved_location_flagged() -> None:
    """Verify that unresolved locations via variables are parsed with placeholders."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    r = next(
        (x for x in model.resources if x.resource_id == "google_bigquery_dataset.unresolved"),
        None,
    )
    assert r is not None
    # Location was var.dataset_location, so should be None
    assert r.region is None
    assert any("Unresolved region reference" in a for a in r.assumptions)


def test_plan_json_resolves_google_bigquery_dataset() -> None:
    """Verify Plan JSON parser extracts dataset resource with location."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/bigquery_plan.json")
    r = next(
        (x for x in model.resources if x.resource_id == "google_bigquery_dataset.with_location"),
        None,
    )
    assert r is not None
    assert r.provider == "gcp"
    assert r.service == "bigquery"
    assert r.kind == "bigquery_dataset"
    assert r.region == "US"


def test_plan_json_resolves_google_bigquery_dataset_with_tables() -> None:
    """Verify Plan JSON ignores table resources and only emits dataset."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/bigquery_plan.json")
    assert len(model.resources) == 1
    assert model.resources[0].resource_id == "google_bigquery_dataset.with_location"
