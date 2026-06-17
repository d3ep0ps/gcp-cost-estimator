# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_hcl_parses_google_filestore_instance() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_filestore_instance.nfs")
    assert res.provider == "gcp"
    assert res.service == "filestore"
    assert res.kind == "google_filestore_instance"
    assert res.region == "us-central1"  # "us-central1-a" zone normalized to region
    assert res.attributes["tier"] == "BASIC_HDD"
    assert float(res.attributes["capacity_gb"]) == 1024.0


def test_plan_json_resolves_google_filestore_instance() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/filestore_plan.json")

    res = next(r for r in model.resources if r.resource_id == "google_filestore_instance.nfs")
    assert res.provider == "gcp"
    assert res.service == "filestore"
    assert res.kind == "google_filestore_instance"
    assert res.region == "us-central1"
    assert res.attributes["tier"] == "BASIC_HDD"
    assert float(res.attributes["capacity_gb"]) == 1024.0
