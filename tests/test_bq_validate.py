from gcp_billing_mcp.core.model import Resource, ResourceModel
from gcp_billing_mcp.core.validate import validate_resource_model


def test_bigquery_dataset_valid_minimal() -> None:
    """Verify minimal bigquery dataset is valid."""
    r = Resource(
        provider="gcp",
        resource_id="my_dataset",
        service="bigquery",
        kind="bigquery_dataset",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_bigquery_dataset_valid_with_usage() -> None:
    """Verify bigquery dataset with explicit usage fields is valid."""
    r = Resource(
        provider="gcp",
        resource_id="my_dataset",
        service="bigquery",
        kind="bigquery_dataset",
        region="US",
        attributes={},
        usage={
            "active_storage_gb": 500.0,
            "long_term_storage_gb": 200.0,
            "monthly_query_tb": 5.0,
            "monthly_streaming_gb": 10.0,
        },
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.region == "us"
    assert norm_r.usage["active_storage_gb"] == 500.0
    assert norm_r.usage["long_term_storage_gb"] == 200.0
    assert norm_r.usage["monthly_query_tb"] == 5.0
    assert norm_r.usage["monthly_streaming_gb"] == 10.0


def test_bigquery_dataset_missing_location_produces_warning() -> None:
    """Verify missing region produces warning, but remains valid."""
    r = Resource(
        provider="gcp",
        resource_id="my_dataset",
        service="bigquery",
        kind="bigquery_dataset",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert any("missing region" in w.lower() for w in res["warnings"])


def test_bigquery_dataset_defaults_all_usage_to_zero_with_assumptions() -> None:
    """Verify representative defaults are applied and recorded in assumptions."""
    r = Resource(
        provider="gcp",
        resource_id="my_dataset",
        service="bigquery",
        kind="bigquery_dataset",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage["active_storage_gb"] == 100
    assert norm_r.usage["long_term_storage_gb"] == 0
    assert norm_r.usage["monthly_query_tb"] == 1
    assert norm_r.usage["monthly_streaming_gb"] == 0

    assert any("Defaulted active_storage_gb to 100" in a for a in norm_r.assumptions)
    assert any("Defaulted long_term_storage_gb to 0" in a for a in norm_r.assumptions)
    assert any("Defaulted monthly_query_tb to 1" in a for a in norm_r.assumptions)
    assert any("Defaulted monthly_streaming_gb to 0" in a for a in norm_r.assumptions)


def test_bigquery_dataset_free_tier_noted_in_assumptions() -> None:
    """Verify BQ free tier disclaimer is added to assumptions."""
    r = Resource(
        provider="gcp",
        resource_id="my_dataset",
        service="bigquery",
        kind="bigquery_dataset",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    norm_r = res["normalized_model"].resources[0]
    assert any("Free tier" in a and "not applied" in a for a in norm_r.assumptions)


def test_bigquery_dataset_capacity_pricing_not_supported_flagged() -> None:
    """Verify that slot/capacity pricing mode is marked as unpriced or warning if specified."""
    # We will check if specifying pricing_model = "capacity" is flagged.
    # Actually, as per BQ-1: "test_bigquery_dataset_capacity_pricing_not_supported_flagged"
    # Let's verify how validate.py behaves or if we add a warning/error, or if it's handled in mapper.
    # The step plan says "test_bigquery_dataset_capacity_pricing_not_supported_flagged". Let's check for a warning
    # in validation, e.g. "Resource has pricing_model 'capacity' which is not supported in v1."
    r = Resource(
        provider="gcp",
        resource_id="my_dataset",
        service="bigquery",
        kind="bigquery_dataset",
        region="us-central1",
        attributes={"pricing_model": "capacity"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert any("capacity" in w.lower() and "pricing" in w.lower() for w in res["warnings"])
