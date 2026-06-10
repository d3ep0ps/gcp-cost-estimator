# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import pytest

from gcp_cost_estimator.mcp.server import mcp

pytestmark = pytest.mark.anyio


async def test_mcp_parse_terraform_extracts_spanner_instance() -> None:
    """Verify that calling the parse_terraform tool returns a resource model with Spanner instance."""
    content, val = await mcp.call_tool(
        "parse_terraform", {"path": "tests/fixtures/terraform", "mode": "auto"}
    )
    assert content is not None
    assert val is not None
    assert "resources" in val

    resources = val["resources"]
    spanner = next(r for r in resources if r["resource_id"] == "google_spanner_instance.spanner_pu")
    assert spanner["provider"] == "gcp"
    assert spanner["service"] == "spanner"
    assert spanner["kind"] == "spanner_instance"


async def test_mcp_validate_resource_model_spanner_defaults_applied() -> None:
    """Verify that calling validate_resource_model applies Spanner defaults."""
    model_dict = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-1",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    content, val = await mcp.call_tool("validate_resource_model", {"model": model_dict})
    assert content is not None
    assert val["valid"] is True
    norm_res = val["normalized_model"]["resources"][0]
    assert norm_res["attributes"]["processing_units"] == 100
    assert norm_res["usage"]["storage_gb"] == 0.0


@patch("gcp_cost_estimator.mcp.server.estimate_infrastructure_core")
async def test_mcp_estimate_infrastructure_spanner_returns_valid_payload(mock_estimate) -> None:
    """Verify that calling estimate_infrastructure with Spanner resource returns valid payload."""
    from gcp_cost_estimator.core.estimate import Estimate

    expected_est = Estimate(
        pricing_snapshot="2026-06-10T12:00:00Z",
        line_items=[],
        monthly_total=0.0,
        unpriced=[],
        assumptions=[],
    )
    mock_estimate.return_value = expected_est

    model_dict = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "spanner-1",
                "service": "spanner",
                "kind": "spanner_instance",
                "region": "us-central1",
                "attributes": {
                    "config": "regional-us-central1",
                },
            }
        ]
    }
    _content, val = await mcp.call_tool("estimate_infrastructure", {"model": model_dict})
    mock_estimate.assert_called_once()
    assert val == expected_est.model_dump()
