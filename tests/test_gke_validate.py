# SPDX-License-Identifier: Apache-2.0

from gcp_billing_mcp.core.model import Resource, ResourceModel
from gcp_billing_mcp.core.validate import validate_resource_model


def test_gke_cluster_valid_minimal() -> None:
    """Verify that a minimal valid GKE cluster passes validation."""
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_gke_cluster_valid_with_machine_type_and_node_count() -> None:
    """Verify that GKE cluster with explicit config passes validation."""
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={
            "machine_type": "n2-standard-4",
            "node_count": 5,
            "disk_size_gb": 200,
            "disk_type": "pd-ssd",
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_gke_cluster_missing_machine_type_flagged_as_warning() -> None:
    """Verify that missing machine_type produces a warning, but is still valid (uses fallback)."""
    # Note: Validate.py warns if machine_type is missing, but falls back to e2-standard-4
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"node_count": 3},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    # The normalizer will add defaulted machine_type to assumptions and validate can warn if desired.
    # We warn that it defaulted to e2-standard-4.
    assert any(
        "defaulted" in w.lower()
        or "missing machine_type" in w.lower()
        or "machine_type" in w.lower()
        for w in res["warnings"]
    )


def test_gke_node_count_defaults_to_3_with_assumption() -> None:
    """Verify GKE node_count defaults to 3 and logs an assumption."""
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["node_count"] == 3
    assert any("Defaulted node_count to 3" in a for a in norm_r.assumptions)


def test_gke_disk_size_defaults_to_100_with_assumption() -> None:
    """Verify GKE disk_size_gb defaults to 100 and logs an assumption."""
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["disk_size_gb"] == 100
    assert any("Defaulted disk_size_gb to 100" in a for a in norm_r.assumptions)


def test_gke_disk_type_defaults_to_pd_standard_with_assumption() -> None:
    """Verify GKE disk_type defaults to pd-standard and logs an assumption."""
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["disk_type"] == "pd-standard"
    assert any("Defaulted disk_type to pd-standard" in a for a in norm_r.assumptions)


def test_gke_node_pool_valid_standalone() -> None:
    """Verify standalone gke_node_pool resource validation and defaults."""
    r = Resource(
        provider="gcp",
        resource_id="pool-1",
        service="container",
        kind="gke_node_pool",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["node_count"] == 3
    assert norm_r.attributes["machine_type"] == "e2-standard-4"
    assert norm_r.attributes["disk_size_gb"] == 100
    assert norm_r.attributes["disk_type"] == "pd-standard"


def test_gke_runtime_defaults_to_730h() -> None:
    """Verify GKE runtime defaults to 730 hours per month."""
    r = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["runtime_hours_per_month"] == 730
    assert any("Defaulted runtime to 730 hours/month" in a for a in norm_r.assumptions)


def test_gke_autopilot_skips_defaults_and_validation() -> None:
    """Verify that Autopilot skips node default attributes injection."""
    r = Resource(
        provider="gcp",
        resource_id="gke-autopilot",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"enable_autopilot": True},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    # Should not have node defaults injected since it's Autopilot
    assert "node_count" not in norm_r.attributes
    assert "machine_type" not in norm_r.attributes
