# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_app_engine_standard_instance_class_resolved_from_enum() -> None:
    """Verify App Engine standard resolves standard instance classes and sets defaults."""
    r = Resource(
        provider="gcp",
        resource_id="ae-std-1",
        service="appengine",
        kind="app_engine_standard_version",
        region="us-central1",
        attributes={
            "instance_class": "F2",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["instance_class"] == "F2"


def test_app_engine_standard_unknown_instance_class_flagged_unpriced() -> None:
    """Verify App Engine standard rejects unknown instance classes."""
    r = Resource(
        provider="gcp",
        resource_id="ae-std-2",
        service="appengine",
        kind="app_engine_standard_version",
        region="us-central1",
        attributes={
            "instance_class": "F9",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is False
    assert any("non-standard instance class" in err.lower() for err in res["errors"])


def test_app_engine_flexible_resources_block_parsed_to_vcpu_ram_disk() -> None:
    """Verify App Engine flexible environment parses cpu, memory_gb, and disk_gb."""
    r = Resource(
        provider="gcp",
        resource_id="ae-flex-1",
        service="appengine",
        kind="app_engine_flexible_version",
        region="us-central1",
        attributes={
            "cpu": 2,
            "memory_gb": 4.0,
            "disk_gb": 20,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["cpu"] == 2
    assert norm_r.attributes["memory_gb"] == 4.0
    assert norm_r.attributes["disk_gb"] == 20


def test_app_engine_flexible_persistent_disk_delegates_to_compute_engine_pd_model() -> None:
    """Verify App Engine flexible environment creates an attached persistent disk resource."""
    r = Resource(
        provider="gcp",
        resource_id="ae-flex-2",
        service="appengine",
        kind="app_engine_flexible_version",
        region="us-central1",
        attributes={
            "cpu": 1,
            "memory_gb": 2.0,
            "disk_gb": 15,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    # Check that an attached disk resource of kind pd_persistent_disk was created
    assert len(norm_r.attached) == 1
    disk = norm_r.attached[0]
    assert disk.kind == "pd_persistent_disk"
    assert disk.attributes["size_gb"] == 15
