# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_hcl_parses_google_alloydb_cluster() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_cluster.alloydb_cluster"
    )
    assert res.provider == "gcp"
    assert res.service == "alloydb"
    assert res.kind == "alloydb_cluster"
    assert res.region == "us-central1"


def test_hcl_parses_google_alloydb_instance_primary() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_instance.alloydb_primary"
    )
    assert res.provider == "gcp"
    assert res.service == "alloydb"
    assert res.kind == "alloydb_instance"
    assert res.attributes["instance_type"] == "PRIMARY"
    assert int(res.attributes["cpu_count"]) == 4


def test_hcl_parses_google_alloydb_instance_read_pool() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_instance.alloydb_read_pool"
    )
    assert res.provider == "gcp"
    assert res.service == "alloydb"
    assert res.kind == "alloydb_instance"
    assert res.attributes["instance_type"] == "READ_POOL"
    assert int(res.attributes["cpu_count"]) == 8
    assert int(res.attributes["node_count"]) == 2


def test_hcl_alloydb_cluster_password_not_extracted_to_model() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_cluster.alloydb_cluster"
    )
    # Rule: Strip password at parse time
    initial_user = res.attributes.get("initial_user", {})
    if initial_user:
        assert "password" not in initial_user or initial_user["password"] == "[REDACTED]"


def test_plan_json_resolves_google_alloydb_cluster() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/alloydb_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_cluster.alloydb_cluster"
    )
    assert res.provider == "gcp"
    assert res.service == "alloydb"
    assert res.kind == "alloydb_cluster"
    assert res.region == "us-central1"


def test_plan_json_resolves_google_alloydb_instance_primary() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/alloydb_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_instance.alloydb_primary"
    )
    assert res.provider == "gcp"
    assert res.service == "alloydb"
    assert res.kind == "alloydb_instance"
    assert res.attributes["instance_type"] == "PRIMARY"
    assert int(res.attributes["cpu_count"]) == 4


def test_plan_json_resolves_google_alloydb_instance_read_pool() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/alloydb_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_alloydb_instance.alloydb_read_pool"
    )
    assert res.provider == "gcp"
    assert res.service == "alloydb"
    assert res.kind == "alloydb_instance"
    assert res.attributes["instance_type"] == "READ_POOL"
    assert int(res.attributes["cpu_count"]) == 8
    assert int(res.attributes["node_count"]) == 2
