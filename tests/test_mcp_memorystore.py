# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import pytest

from gcp_cost_estimator.mcp.server import mcp

pytestmark = pytest.mark.anyio


async def test_mcp_parse_terraform_extracts_memorystore() -> None:
    """Verify that calling the parse_terraform tool returns a resource model with Redis and Valkey instances."""
    content, val = await mcp.call_tool(
        "parse_terraform", {"path": "tests/fixtures/terraform", "mode": "auto"}
    )
    assert content is not None
    assert val is not None
    assert "resources" in val

    resources = val["resources"]
    redis = next(r for r in resources if r["resource_id"] == "google_redis_instance.redis_basic")
    assert redis["provider"] == "gcp"
    assert redis["service"] == "memorystore"
    assert redis["kind"] == "redis_instance"

    valkey = next(
        r for r in resources if r["resource_id"] == "google_memorystore_instance.valkey_cluster"
    )
    assert valkey["provider"] == "gcp"
    assert valkey["service"] == "memorystore"
    assert valkey["kind"] == "memorystore_instance"


async def test_mcp_validate_resource_model_redis_defaults_applied() -> None:
    """Verify that calling validate_resource_model applies Redis defaults."""
    model_dict = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "redis-1",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5,
                },
            }
        ]
    }
    content, val = await mcp.call_tool("validate_resource_model", {"model": model_dict})
    assert content is not None
    assert val["valid"] is True
    norm_res = val["normalized_model"]["resources"][0]
    assert norm_res["attributes"]["tier"] == "BASIC"


@patch("gcp_cost_estimator.mcp.server.estimate_infrastructure_core")
async def test_mcp_estimate_infrastructure_redis_returns_valid_payload(mock_estimate) -> None:
    """Verify that calling estimate_infrastructure with Redis resource returns valid payload."""
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
                "resource_id": "redis-1",
                "service": "memorystore",
                "kind": "redis_instance",
                "region": "us-central1",
                "attributes": {
                    "memory_size_gb": 5,
                },
            }
        ]
    }
    _content, val = await mcp.call_tool("estimate_infrastructure", {"model": model_dict})
    mock_estimate.assert_called_once()
    assert val == expected_est.model_dump()
