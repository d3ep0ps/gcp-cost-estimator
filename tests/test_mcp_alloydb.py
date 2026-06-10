# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import pytest

from gcp_cost_estimator.mcp.server import mcp

pytestmark = pytest.mark.anyio


async def test_mcp_parse_terraform_extracts_alloydb_cluster_and_instance() -> None:
    """Verify that calling the parse_terraform tool returns a resource model with AlloyDB cluster & instance."""
    content, val = await mcp.call_tool(
        "parse_terraform", {"path": "tests/fixtures/terraform", "mode": "auto"}
    )
    assert content is not None
    assert val is not None
    assert "resources" in val

    resources = val["resources"]
    cluster = next(
        r for r in resources if r["resource_id"] == "google_alloydb_cluster.alloydb_cluster"
    )
    assert cluster["provider"] == "gcp"
    assert cluster["service"] == "alloydb"
    assert cluster["kind"] == "alloydb_cluster"

    instance = next(
        r for r in resources if r["resource_id"] == "google_alloydb_instance.alloydb_primary"
    )
    assert instance["provider"] == "gcp"
    assert instance["service"] == "alloydb"
    assert instance["kind"] == "alloydb_instance"


async def test_mcp_validate_resource_model_alloydb_sensitive_field_redacted() -> None:
    """Verify that calling validate_resource_model redacts sensitive fields like passwords."""
    model_dict = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "alloydb-cluster-1",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
                "attributes": {"initial_user": {"password": "super-secret-password"}},
            }
        ]
    }
    content, val = await mcp.call_tool("validate_resource_model", {"model": model_dict})
    assert content is not None
    assert val["valid"] is True
    norm_res = val["normalized_model"]["resources"][0]
    initial_user = norm_res["attributes"].get("initial_user", {})
    assert "password" not in initial_user or initial_user["password"] == "[REDACTED]"


@patch("gcp_cost_estimator.mcp.server.estimate_infrastructure_core")
async def test_mcp_estimate_infrastructure_alloydb_returns_valid_payload(mock_estimate) -> None:
    """Verify that calling estimate_infrastructure with AlloyDB resource returns valid payload."""
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
                "resource_id": "alloydb-cluster-1",
                "service": "alloydb",
                "kind": "alloydb_cluster",
                "region": "us-central1",
            }
        ]
    }
    _content, val = await mcp.call_tool("estimate_infrastructure", {"model": model_dict})
    mock_estimate.assert_called_once()
    assert val == expected_est.model_dump()
