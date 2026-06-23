# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest

from gcp_cost_estimator.core.estimate import Estimate
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.mcp.server import get_default_db_path, mcp

pytestmark = pytest.mark.anyio


def test_get_default_db_path_resolves_correctly(tmp_path, monkeypatch) -> None:
    """Verifies that the DB path resolves to env var if present, else user home fallback."""
    # Test Env Var
    test_db_path = str(tmp_path / "env_db.sqlite")
    monkeypatch.setenv("GCP_BILLING_DB_PATH", test_db_path)
    assert get_default_db_path() == test_db_path

    # Test Fallback (remove env var)
    monkeypatch.delenv("GCP_BILLING_DB_PATH", raising=False)
    fake_home = tmp_path / "fake_home"
    with patch("pathlib.Path.home", return_value=fake_home):
        resolved = get_default_db_path()
        assert "pricing.sqlite" in resolved
        assert str(fake_home) in resolved


async def test_mcp_tools_are_registered() -> None:
    """Verifies all expected tools are registered on the FastMCP instance."""
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "parse_terraform",
        "validate_resource_model",
        "estimate_infrastructure",
        "render_estimate",
        "get_cache_status",
        "refresh_pricing_cache",
        "compare_regions",
        "compare_estimates",
        "what_if",
        "suggest_cheaper_machine_types",
        "find_unpriced",
    }
    assert expected_tools.issubset(tool_names)


async def test_mcp_resources_are_registered() -> None:
    """Verifies all expected resources are registered on the FastMCP instance."""
    resources = await mcp.list_resources()
    resource_uris = {str(r.uri) for r in resources}

    expected_uris = {
        "schema://resource-model",
        "catalog://coverage",
        "catalog://defaults",
        "pricing://snapshot",
        "docs://disclaimer",
    }
    assert expected_uris.issubset(resource_uris)


async def test_mcp_prompts_are_registered() -> None:
    """Verifies all expected prompts are registered on the FastMCP instance."""
    prompts = await mcp.list_prompts()
    prompt_names = {p.name for p in prompts}

    expected_prompts = {
        "estimate-from-description",
        "estimate-from-terraform",
        "explain-estimate",
        "optimize-cost",
    }
    assert expected_prompts.issubset(prompt_names)


def test_parse_terraform_rejects_path_outside_allowed_dir(tmp_path, monkeypatch) -> None:
    """parse_terraform raises ValueError for paths outside GCP_PARSE_ALLOWED_DIR."""
    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    import gcp_cost_estimator.mcp.server as srv

    srv._PARSE_ALLOWED_DIR = str(safe_dir)

    with pytest.raises(ValueError, match="outside the allowed directory"):
        srv.parse_terraform(path="/etc")

    # Restore
    srv._PARSE_ALLOWED_DIR = None


def test_parse_terraform_allows_allowed_dir_itself(tmp_path, monkeypatch) -> None:
    """parse_terraform must not reject the allowed directory itself (startswith + os.sep bug)."""
    safe_dir = tmp_path / "workspace"
    safe_dir.mkdir()
    import gcp_cost_estimator.mcp.server as srv
    from unittest.mock import patch

    srv._PARSE_ALLOWED_DIR = str(safe_dir)
    # parse_terraform_core will fail (dir has no TF files) but the path guard must NOT raise.
    # We patch core to isolate the guard logic.
    with patch("gcp_cost_estimator.mcp.server.parse_terraform_core", return_value=None):
        result = srv.parse_terraform(path=str(safe_dir))
    assert result is None  # guard passed, core was called

    # Restore
    srv._PARSE_ALLOWED_DIR = None


@patch("gcp_cost_estimator.mcp.server.parse_terraform_core")
async def test_tool_parse_terraform(mock_parse) -> None:
    """Verifies that the parse_terraform tool delegates correctly to core."""
    mock_model = ResourceModel(resources=[])
    mock_parse.return_value = mock_model

    content, val = await mcp.call_tool("parse_terraform", {"path": "/fake/path", "mode": "auto"})
    # Verify delegation
    mock_parse.assert_called_once_with("/fake/path", mode="auto")
    # Verify result is serialized
    assert content is not None
    assert val == {"resources": []}
    assert any("resources" in getattr(c, "text", "") for c in content)


@patch("gcp_cost_estimator.mcp.server.validate_resource_model_core")
async def test_tool_validate_resource_model(mock_validate) -> None:
    """Verifies that the validate_resource_model tool delegates to core."""
    expected_val = {"valid": True, "errors": [], "warnings": []}
    mock_validate.return_value = expected_val

    content, val = await mcp.call_tool("validate_resource_model", {"model": {"resources": []}})
    mock_validate.assert_called_once()
    assert content is not None
    assert val == expected_val
    assert any("valid" in getattr(c, "text", "") for c in content)


@patch("gcp_cost_estimator.mcp.server.estimate_infrastructure_core")
async def test_tool_estimate_infrastructure(mock_estimate) -> None:
    """Verifies that the estimate_infrastructure tool delegates to core."""
    expected_val = Estimate(
        pricing_snapshot="2026-06-03T12:00:00Z",
        line_items=[],
        monthly_total=0.0,
        unpriced=[],
        assumptions=[],
    )
    mock_estimate.return_value = expected_val

    content, val = await mcp.call_tool("estimate_infrastructure", {"model": {"resources": []}})
    mock_estimate.assert_called_once()
    assert content is not None
    # FastMCP converts Pydantic return values to dictionary representation
    assert val == expected_val.model_dump()


@patch("gcp_cost_estimator.mcp.server.get_output_renderer")
async def test_tool_render_estimate(mock_get_renderer) -> None:
    """Verifies that the render_estimate tool delegates to registries."""
    mock_renderer = MagicMock()
    mock_renderer.render.return_value = "rendered_markdown_output"
    mock_get_renderer.return_value = mock_renderer

    estimate_dict = {
        "pricing_snapshot": "2026-06-03T12:00:00Z",
        "line_items": [],
        "monthly_total": 0.0,
        "unpriced": [],
        "assumptions": [],
    }
    content, val = await mcp.call_tool(
        "render_estimate", {"estimate": estimate_dict, "format": "markdown"}
    )
    mock_get_renderer.assert_called_once_with("markdown")
    mock_renderer.render.assert_called_once()
    assert content is not None
    assert val == {"result": "rendered_markdown_output"}
    assert any("rendered_markdown_output" in getattr(c, "text", "") for c in content)


@patch("gcp_cost_estimator.mcp.server.get_cache_status_core")
async def test_tool_get_cache_status(mock_get_status) -> None:
    """Verifies that the get_cache_status tool delegates to core."""
    expected_val = {"sku_count": 42}
    mock_get_status.return_value = expected_val

    content, val = await mcp.call_tool("get_cache_status", {"provider": "gcp"})
    mock_get_status.assert_called_once()
    assert content is not None
    assert val == expected_val
    assert any("42" in getattr(c, "text", "") for c in content)


@patch("gcp_cost_estimator.mcp.server.refresh_pricing_cache_core")
async def test_tool_refresh_pricing_cache(mock_refresh) -> None:
    """Verifies that the refresh_pricing_cache tool delegates to core."""
    expected_val = {"status": "success"}
    mock_refresh.return_value = expected_val

    content, val = await mcp.call_tool("refresh_pricing_cache", {"provider": "gcp", "force": True})
    mock_refresh.assert_called_once()
    assert content is not None
    assert val == expected_val
    assert any("success" in getattr(c, "text", "") for c in content)


async def test_resource_reading() -> None:
    """Verifies registered resources can be read."""
    contents = await mcp.read_resource("docs://disclaimer")
    assert contents is not None
    assert any("List price only" in getattr(c, "content", "") for c in contents)

    schema_contents = await mcp.read_resource("schema://resource-model")
    assert schema_contents is not None
    assert any("properties" in getattr(c, "content", "") for c in schema_contents)

    coverage_contents = await mcp.read_resource("catalog://coverage")
    assert coverage_contents is not None
    assert any("cloud_sql_instance" in getattr(c, "content", "") for c in coverage_contents)


async def test_prompts_fetching() -> None:
    """Verifies registered prompts can be retrieved."""
    prompt = await mcp.get_prompt("explain-estimate", {"estimate_json": "{}"})
    assert prompt is not None
    assert len(prompt.messages) > 0
    assert "explain" in prompt.messages[0].content.text.lower()


async def test_prompts_fetching_without_arguments() -> None:
    """Verifies prompts can be retrieved without optional arguments instead of raising errors."""
    prompt = await mcp.get_prompt("estimate-from-description", {})
    assert prompt is not None
    assert "description" in prompt.messages[0].content.text


async def test_stdio_smoke_test() -> None:
    """Verifies the server starts up and serves tools/resources over stdio transport."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "gcp_cost_estimator.mcp.server"],
    )
    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        # 1. Check tools
        tools_result = await session.list_tools()
        tool_names = {t.name for t in tools_result.tools}
        assert "parse_terraform" in tool_names
        assert "estimate_infrastructure" in tool_names
        assert "compare_regions" in tool_names
        assert "suggest_cheaper_machine_types" in tool_names

        # 2. Check resources
        resources_result = await session.list_resources()
        resource_uris = {str(r.uri) for r in resources_result.resources}
        assert "docs://disclaimer" in resource_uris


@patch("gcp_cost_estimator.mcp.server.compare_regions_core")
async def test_tool_compare_regions(mock_compare) -> None:
    """Verifies that the compare_regions tool delegates correctly to core."""
    expected_val = {"cheapest_region": "us-central1", "estimates": {}}
    mock_compare.return_value = expected_val

    _content, val = await mcp.call_tool(
        "compare_regions", {"model": {"resources": []}, "regions": ["us-central1"]}
    )
    mock_compare.assert_called_once()
    assert val == expected_val


@patch("gcp_cost_estimator.mcp.server.compare_estimates_core")
async def test_tool_compare_estimates(mock_compare) -> None:
    """Verifies that the compare_estimates tool delegates correctly to core."""
    expected_val = {"monthly_total_diff": 10.0}
    mock_compare.return_value = expected_val

    estimate_dict = {
        "pricing_snapshot": "2026-06-03T12:00:00Z",
        "line_items": [],
        "monthly_total": 0.0,
        "unpriced": [],
        "assumptions": [],
    }
    _content, val = await mcp.call_tool(
        "compare_estimates", {"estimate_a": estimate_dict, "estimate_b": estimate_dict}
    )
    mock_compare.assert_called_once()
    assert val == expected_val


@patch("gcp_cost_estimator.mcp.server.what_if_core")
async def test_tool_what_if(mock_what_if) -> None:
    """Verifies that the what_if tool delegates correctly to core."""
    expected_val = {"comparison": {}}
    mock_what_if.return_value = expected_val

    _content, val = await mcp.call_tool("what_if", {"model": {"resources": []}, "changes": {}})
    mock_what_if.assert_called_once()
    assert val == expected_val


@patch("gcp_cost_estimator.mcp.server.suggest_cheaper_machine_types_core")
async def test_tool_suggest_cheaper_machine_types(mock_suggest) -> None:
    """Verifies that the suggest_cheaper_machine_types tool delegates correctly to core."""
    expected_val = [{"machine_type": "e2-standard-4"}]
    mock_suggest.return_value = expected_val

    resource_dict = {
        "provider": "gcp",
        "resource_id": "vm-1",
        "service": "compute",
        "kind": "gce_instance",
        "region": "us-central1",
        "attributes": {"machine_type": "n2-standard-4"},
    }
    _content, val = await mcp.call_tool(
        "suggest_cheaper_machine_types", {"resource": resource_dict}
    )
    mock_suggest.assert_called_once()
    assert val == {"result": expected_val}


@patch("gcp_cost_estimator.mcp.server.find_unpriced_core")
async def test_tool_find_unpriced(mock_find) -> None:
    """Verifies that the find_unpriced tool delegates correctly to core."""
    expected_val = [{"resource_id": "vm-1", "reason": "unmapped"}]
    mock_find.return_value = expected_val

    _content, val = await mcp.call_tool("find_unpriced", {"model": {"resources": []}})
    mock_find.assert_called_once()
    assert val == {"result": expected_val}
