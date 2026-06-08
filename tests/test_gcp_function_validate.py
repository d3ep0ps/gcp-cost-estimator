# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_cloud_function_1st_gen_instance_class_resolved_from_memory_mb() -> None:
    """Verify that a 1st gen Cloud Function resolves to a standard instance class from memory_mb."""
    r = Resource(
        provider="gcp",
        resource_id="fn-1",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["available_memory_mb"] == 256
    assert norm_r.attributes["memory_gb"] == 0.25
    assert norm_r.attributes["cpu_ghz"] == 0.4


def test_cloud_function_1st_gen_non_standard_memory_flagged_unpriced() -> None:
    """Verify that a 1st gen Cloud Function with non-standard memory fails validation or is flagged as invalid/unpriced."""
    r = Resource(
        provider="gcp",
        resource_id="fn-2",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 999,
            "generation": "1st_gen",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    # The plan says: "if the value does not match a published class exactly, surface as unpriced with reason
    # 'non-standard memory allocation for 1st-gen function' rather than guessing".
    # So we can keep it as valid but put a check in mapper, or flag it as validation error/unpriced. Let's make it a validation error
    # or ensure it gets captured in unpriced. In validate, let's append an error.
    assert res["valid"] is False
    assert any("non-standard memory" in err.lower() for err in res["errors"])


def test_cloud_function_2nd_gen_delegates_to_cloud_run_resource_shape() -> None:
    """Verify that 2nd-gen function transforms its memory and CPU limits to Cloud Run shape."""
    r = Resource(
        provider="gcp",
        resource_id="fn-3",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory": "512Mi",
            "available_cpu": "1",
            "generation": "2nd_gen",
            "min_instance_count": 1,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    # Check that it converted available_memory/available_cpu to cpu/memory limits (Cloud Run shape)
    # and min_instance_count is preserved
    assert norm_r.attributes["cpu"] == "1"
    assert norm_r.attributes["memory"] == "0.5"
    assert norm_r.attributes["min_instance_count"] == 1
    assert norm_r.attributes["cpu_idle"] is True


def test_cloud_function_missing_invocation_usage_applies_representative_default() -> None:
    """Verify representative defaults are set and assumptions recorded for invocations."""
    r = Resource(
        provider="gcp",
        resource_id="fn-4",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["invocations_per_month"] == 1000000
    assert norm_r.usage["avg_execution_time_ms"] == 100.0
    assert any("Defaulted invocations_per_month" in a for a in norm_r.assumptions)


def test_cloud_function_min_instances_enables_idle_billing_assumption() -> None:
    """Verify that min_instances > 0 on 1st gen adds idle billing assumption."""
    r = Resource(
        provider="gcp",
        resource_id="fn-5",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
            "min_instances": 1,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["min_instances"] == 1
    assert any("min_instances" in a for a in norm_r.assumptions)
