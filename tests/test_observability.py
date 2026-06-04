import logging
from unittest.mock import patch

from gcp_billing_mcp.core.estimate import Estimate
from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.service import estimate_infrastructure
from gcp_billing_mcp.mcp.server import validate_resource_model


@patch("gcp_billing_mcp.core.service.get_cache_status")
def test_stale_cache_adds_warning_to_estimate(mock_get_status) -> None:
    """Verify that a stale cache (older than 72 hours) adds a warning to assumptions."""
    mock_get_status.return_value = {
        "provider": "gcp",
        "last_refreshed_at": "2026-06-01T12:00:00Z",
        "age_hours": 80.0,
        "sku_count": 100,
        "stale": True,
    }

    model = ResourceModel(resources=[])
    estimate = estimate_infrastructure("/fake/db.sqlite", model)

    assert isinstance(estimate, Estimate)
    # Check that the stale cache warning is in the assumptions
    warning_exists = any(
        "Pricing cache is stale" in assumption and "2026-06-01T12:00:00Z" in assumption
        for assumption in estimate.assumptions
    )
    assert warning_exists, f"Stale warning missing in assumptions: {estimate.assumptions}"


def test_per_tool_timing_logged_structured(caplog) -> None:
    """Verify that calling an MCP tool logs execution status and duration in a structured way."""
    caplog.set_level(logging.INFO, logger="gcp_billing_mcp")

    # Call a decorated tool from server
    model = ResourceModel(resources=[])
    validate_resource_model(model)

    # Assert that a structured timing log exists
    found_log = False
    for record in caplog.records:
        if "MCP Tool Executed:" in record.message:
            assert "tool=validate_resource_model" in record.message
            assert "status=success" in record.message
            assert "duration_ms=" in record.message
            found_log = True
            break

    assert found_log, f"Expected timing log not found. Logs: {[r.message for r in caplog.records]}"
