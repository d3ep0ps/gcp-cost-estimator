# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_hcl_parses_google_firestore_database_native() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_firestore_database.firestore_native"
    )
    assert res.provider == "gcp"
    assert res.service == "firestore"
    assert res.kind == "firestore_database"
    assert res.region == "us-central"  # location_id
    assert res.attributes["database_type"] == "FIRESTORE_NATIVE"


def test_hcl_parses_google_firestore_database_datastore_mode() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_firestore_database.firestore_datastore"
    )
    assert res.provider == "gcp"
    assert res.service == "firestore"
    assert res.kind == "firestore_database"
    assert res.region == "europe-west"
    assert res.attributes["database_type"] == "DATASTORE_MODE"


def test_hcl_firestore_missing_type_defaults_to_native() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_firestore_database.firestore_default_type"
    )
    assert "database_type" not in res.attributes  # default applied in validate

    single_model = ResourceModel(resources=[res])
    result = validate_resource_model(single_model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].attributes["database_type"] == "FIRESTORE_NATIVE"


def test_hcl_firestore_location_id_normalised() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_firestore_database.firestore_native"
    )
    single_model = ResourceModel(resources=[res])
    result = validate_resource_model(single_model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].region == "us-central1"


def test_hcl_firestore_unresolved_var_in_location_flagged() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_firestore_database.firestore_unresolved"
    )
    assert any("unresolved attribute location_id" in a.lower() for a in res.assumptions)


def test_plan_json_resolves_google_firestore_database() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/firestore_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_firestore_database.firestore_native"
    )
    assert res.provider == "gcp"
    assert res.service == "firestore"
    assert res.kind == "firestore_database"
    assert res.region == "us-central"
    assert res.attributes["database_type"] == "FIRESTORE_NATIVE"

    single_model = ResourceModel(resources=[res])
    result = validate_resource_model(single_model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].region == "us-central1"
