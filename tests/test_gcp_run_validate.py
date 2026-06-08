# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_cloud_run_service_request_based_billing_recorded() -> None:
    """Verify standard Cloud Run service request-based billing defaults to CPU idle true."""
    r = Resource(
        provider="gcp",
        resource_id="run-service-1",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "512Mi",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["cpu_idle"] is True
    assert norm_r.attributes["min_instance_count"] == 0
    assert norm_r.usage["runtime_seconds_per_invocation"] == 1.0
    assert norm_r.usage["invocations_per_month"] == 10000


def test_cloud_run_service_instance_based_billing_recorded() -> None:
    """Verify Cloud Run service instance-based billing preserves CPU idle false."""
    r = Resource(
        provider="gcp",
        resource_id="run-service-2",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "2000m",
            "memory": "2Gi",
            "cpu_idle": False,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["cpu_idle"] is False
    assert norm_r.attributes["cpu"] == "2"
    assert norm_r.attributes["memory"] == "2.0"


def test_cloud_run_service_min_instances_enables_idle_billing_assumption() -> None:
    """Verify that setting min_instance_count > 0 adds an assumption for idle instance billing."""
    r = Resource(
        provider="gcp",
        resource_id="run-service-3",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "512Mi",
            "min_instance_count": 2,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["min_instance_count"] == 2
    assert any("min_instance_count" in a for a in norm_r.assumptions)


def test_cloud_run_service_cpu_memory_quantities_parsed_from_k8s_strings() -> None:
    """Verify quantity parsing for various k8s formats."""
    r = Resource(
        provider="gcp",
        resource_id="run-service-4",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "4000m",
            "memory": "512Mi",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["cpu"] == "4"
    assert norm_r.attributes["memory"] == "0.5"


def test_cloud_run_job_requires_task_count_and_runtime_usage_fields() -> None:
    """Verify basic validation on Cloud Run job resource config."""
    r = Resource(
        provider="gcp",
        resource_id="run-job-1",
        service="run",
        kind="cloud_run_job",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "512Mi",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["task_count"] == 1
    assert norm_r.usage["runtime_seconds_per_task"] == 60
    assert norm_r.usage["executions_per_month"] == 100


def test_cloud_run_job_missing_usage_flagged_with_representative_defaults() -> None:
    """Verify representative defaults are set and recorded in assumptions for run job."""
    r = Resource(
        provider="gcp",
        resource_id="run-job-2",
        service="run",
        kind="cloud_run_job",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "1Gi",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert any("Defaulted task_count" in a for a in norm_r.assumptions)
    assert any("Defaulted executions_per_month" in a for a in norm_r.assumptions)


def test_cloud_run_gpu_attributes_recorded_when_present() -> None:
    """Verify GPU type and count are preserved in attributes."""
    r = Resource(
        provider="gcp",
        resource_id="run-service-5",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "4",
            "memory": "16Gi",
            "gpu_type": "nvidia-l4",
            "gpu_count": 1,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["gpu_type"] == "nvidia-l4"
    assert norm_r.attributes["gpu_count"] == 1


def test_cloud_run_unknown_region_flagged_unpriced_not_guessed() -> None:
    """Verify warning is produced when region is empty/unspecified."""
    r = Resource(
        provider="gcp",
        resource_id="run-service-6",
        service="run",
        kind="cloud_run_service",
        attributes={
            "cpu": "1",
            "memory": "512Mi",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert any("missing region" in w.lower() for w in res["warnings"])
