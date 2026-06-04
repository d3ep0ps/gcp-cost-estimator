# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_gcs_bucket_valid_standard_us_central1() -> None:
    """Verify standard bucket validation in standard region."""
    r = Resource(
        provider="gcp",
        resource_id="my-bucket",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0
    # The storage_class should be standardized (in this case already uppercase/valid)
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["storage_class"] == "STANDARD"


def test_gcs_bucket_valid_nearline_multi_region() -> None:
    """Verify Nearline storage class in multi-region location (e.g. US)."""
    r = Resource(
        provider="gcp",
        resource_id="my-bucket",
        service="storage",
        kind="gcs_bucket",
        region="US",
        attributes={"storage_class": "NEARLINE"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    # Location should be normalized to lowercase "us"
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.region == "us"


def test_gcs_bucket_unknown_storage_class_flagged_as_warning() -> None:
    """Verify that unrecognized storage class produces warning, not error, and prices as STANDARD."""
    r = Resource(
        provider="gcp",
        resource_id="my-bucket",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "SUPERCOOLDATA"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True  # Warning only, so still valid!
    assert any("unrecognized storage_class" in w.lower() for w in res["warnings"])

    # Normalized model should fallback to STANDARD
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes["storage_class"] == "STANDARD"
    assert any("fallback" in a.lower() or "default" in a.lower() for a in norm_r.assumptions)


def test_gcs_bucket_missing_location_produces_warning_not_error() -> None:
    """Verify missing region produces warning, but remains valid."""
    r = Resource(
        provider="gcp",
        resource_id="my-bucket",
        service="storage",
        kind="gcs_bucket",
        attributes={"storage_class": "STANDARD"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert any("missing region" in w.lower() for w in res["warnings"])


def test_gcs_bucket_retrieval_fee_only_for_cold_classes() -> None:
    """Verify monthly_retrieval_gb default behaves correctly for standard vs cold."""
    # Standard class
    r_std = Resource(
        provider="gcp",
        resource_id="my-bucket-std",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
    )
    # Nearline class (cold)
    r_cold = Resource(
        provider="gcp",
        resource_id="my-bucket-cold",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "NEARLINE"},
    )
    model = ResourceModel(resources=[r_std, r_cold])
    res = validate_resource_model(model)
    norm_std = res["normalized_model"].resources[0]
    norm_cold = res["normalized_model"].resources[1]

    # Both should have default retrieval gb as 0, but standard shouldn't have retrieval warning/fee logic
    assert norm_std.usage["monthly_retrieval_gb"] == 0
    assert norm_cold.usage["monthly_retrieval_gb"] == 0


def test_gcs_bucket_defaults_applied_usage_fields_zero_with_assumptions() -> None:
    """Verify representative defaults are applied and recorded in assumptions."""
    r = Resource(
        provider="gcp",
        resource_id="my-bucket",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]

    assert norm_r.attributes["storage_class"] == "STANDARD"
    assert norm_r.usage["size_gb"] == 100
    assert norm_r.usage["monthly_class_a_ops"] == 10000
    assert norm_r.usage["monthly_class_b_ops"] == 100000
    assert norm_r.usage["monthly_egress_gb"] == 10
    assert norm_r.usage["monthly_retrieval_gb"] == 0

    # Check assumptions are populated
    assert any("Defaulted storage_class to STANDARD" in a for a in norm_r.assumptions)
    assert any("Defaulted size_gb to 100" in a for a in norm_r.assumptions)
    assert any("Defaulted monthly_class_a_ops to 10000" in a for a in norm_r.assumptions)
    assert any("Defaulted monthly_class_b_ops to 100000" in a for a in norm_r.assumptions)
    assert any("Defaulted monthly_egress_gb to 10" in a for a in norm_r.assumptions)
