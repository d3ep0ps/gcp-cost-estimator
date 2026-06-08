# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_parse_cloud_run_v2_service_extracts_cpu_memory_and_scaling() -> None:
    """Verify HCL parser extracts CPU/Memory limits and scaling min/max instances for Cloud Run service."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_cloud_run_v2_service.example")
    assert res.provider == "gcp"
    assert res.service == "run"
    assert res.kind == "cloud_run_service"
    assert res.region == "us-central1"
    assert res.attributes["cpu"] == "2"
    assert res.attributes["memory"] == "4Gi"
    assert res.attributes.get("min_instance_count") == 2
    assert res.attributes.get("max_instance_count") == 10


def test_parse_cloud_run_v2_job_extracts_task_template_and_retries() -> None:
    """Verify HCL parser extracts CPU/Memory limits for Cloud Run jobs."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_cloud_run_v2_job.example")
    assert res.provider == "gcp"
    assert res.service == "run"
    assert res.kind == "cloud_run_job"
    assert res.region == "us-central1"
    assert res.attributes["cpu"] == "1"
    assert res.attributes["memory"] == "512Mi"


def test_parse_cloud_run_unresolved_variable_in_cpu_flagged_not_assumed() -> None:
    """Verify that unresolved variables in limits configuration are flagged in assumptions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_cloud_run_v2_service.unresolved"
    )
    assert any("unresolved attribute" in a.lower() for a in res.assumptions)


def test_plan_json_resolves_cloud_run_resources() -> None:
    """Verify plan JSON parser extracts service/job locations, limits, and scaling."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/run_plan.json")

    service = next(
        r for r in model.resources if r.resource_id == "google_cloud_run_v2_service.example"
    )
    assert service.provider == "gcp"
    assert service.service == "run"
    assert service.kind == "cloud_run_service"
    assert service.region == "us-central1"
    assert service.attributes["cpu"] == "2"
    assert service.attributes["memory"] == "4Gi"
    assert service.attributes.get("min_instance_count") == 2
    assert service.attributes.get("max_instance_count") == 10

    job = next(r for r in model.resources if r.resource_id == "google_cloud_run_v2_job.example")
    assert job.provider == "gcp"
    assert job.service == "run"
    assert job.kind == "cloud_run_job"
    assert job.region == "us-central1"
    assert job.attributes["cpu"] == "1"
    assert job.attributes["memory"] == "512Mi"
