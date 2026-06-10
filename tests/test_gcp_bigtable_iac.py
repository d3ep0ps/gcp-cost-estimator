# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_hcl_parses_google_bigtable_instance_single_cluster() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_bigtable_instance.bigtable_ssd"
    )
    assert res.provider == "gcp"
    assert res.service == "bigtable"
    assert res.kind == "bigtable_instance"
    assert res.attributes["instance_type"] == "PRODUCTION"

    clusters = res.attributes["clusters"]
    assert len(clusters) == 1
    assert clusters[0]["cluster_id"] == "cluster-1"
    assert clusters[0]["zone"] == "us-central1-a"
    assert int(clusters[0]["num_nodes"]) == 3
    assert clusters[0]["storage_type"] == "SSD"


def test_hcl_parses_google_bigtable_instance_multi_cluster() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_bigtable_instance.bigtable_multi"
    )
    assert res.provider == "gcp"
    assert res.service == "bigtable"
    assert res.kind == "bigtable_instance"

    clusters = res.attributes["clusters"]
    assert len(clusters) == 2
    assert clusters[0]["cluster_id"] == "cluster-1"
    assert clusters[1]["cluster_id"] == "cluster-2"
    assert int(clusters[1]["num_nodes"]) == 4


def test_hcl_bigtable_zone_converted_to_region() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_bigtable_instance.bigtable_ssd"
    )
    single_model = ResourceModel(resources=[res])
    result = validate_resource_model(single_model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["clusters"][0]["region"] == "us-central1"


def test_hcl_bigtable_development_instance_parsed() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_bigtable_instance.bigtable_dev"
    )
    assert res.attributes["instance_type"] == "DEVELOPMENT"
    clusters = res.attributes["clusters"]
    assert len(clusters) == 1
    # num_nodes is absent in HCL, should be defaulted to 1 during validate
    single_model = ResourceModel(resources=[res])
    result = validate_resource_model(single_model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].attributes["clusters"][0]["num_nodes"] == 1


def test_plan_json_resolves_google_bigtable_instance() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/bigtable_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_bigtable_instance.bigtable_ssd"
    )
    assert res.provider == "gcp"
    assert res.service == "bigtable"
    assert res.kind == "bigtable_instance"
    assert res.attributes["instance_type"] == "PRODUCTION"

    clusters = res.attributes["clusters"]
    assert len(clusters) == 1
    assert clusters[0]["cluster_id"] == "cluster-1"
    assert clusters[0]["zone"] == "us-central1-a"
    assert int(clusters[0]["num_nodes"]) == 3
    assert clusters[0]["storage_type"] == "SSD"


def test_plan_json_resolves_bigtable_multi_cluster() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/bigtable_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_bigtable_instance.bigtable_multi"
    )
    assert res.provider == "gcp"
    assert res.service == "bigtable"
    assert res.kind == "bigtable_instance"

    clusters = res.attributes["clusters"]
    assert len(clusters) == 2
    assert clusters[0]["cluster_id"] == "cluster-1"
    assert clusters[1]["cluster_id"] == "cluster-2"
    assert int(clusters[1]["num_nodes"]) == 4
