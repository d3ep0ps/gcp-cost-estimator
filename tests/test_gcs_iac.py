# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_hcl_parses_google_storage_bucket_standard() -> None:
    """Verify standard bucket parses location as 'US' and storage class standard."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    # Find google_storage_bucket.standard
    res = next(r for r in model.resources if r.resource_id == "google_storage_bucket.standard")
    assert res.provider == "gcp"
    assert res.service == "storage"
    assert res.kind == "gcs_bucket"
    assert res.region == "US"
    assert res.attributes["storage_class"] == "STANDARD"


def test_hcl_parses_nearline_bucket_with_location() -> None:
    """Verify Nearline bucket location and storage class mapping."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_storage_bucket.nearline")
    assert res.region == "us-central1"
    assert res.attributes["storage_class"] == "NEARLINE"


def test_hcl_parses_archive_bucket() -> None:
    """Verify Archive bucket location and storage class mapping."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_storage_bucket.archive")
    assert res.region == "europe-west1"
    assert res.attributes["storage_class"] == "ARCHIVE"


def test_hcl_missing_storage_class_defaults_to_standard() -> None:
    """Verify bucket with missing storage class parses fine (defaults applied by validate)."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_storage_bucket.default_class")
    assert res.region == "asia-east1"
    assert "storage_class" not in res.attributes


def test_hcl_unresolved_var_in_location_flagged() -> None:
    """Verify that unresolved variables in location attribute are flagged in assumptions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_storage_bucket.unresolved")
    assert res.region is None
    assert any("Unresolved region reference" in a for a in res.assumptions)


def test_plan_json_resolves_google_storage_bucket() -> None:
    """Verify standard bucket parses correctly from plan JSON file."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/gcs_plan.json")

    res = next(r for r in model.resources if r.resource_id == "google_storage_bucket.standard")
    assert res.provider == "gcp"
    assert res.service == "storage"
    assert res.kind == "gcs_bucket"
    assert res.region == "US"
    assert res.attributes["storage_class"] == "STANDARD"
