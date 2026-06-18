# SPDX-License-Identifier: Apache-2.0

import functools
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from gcp_cost_estimator.core.advisory import (
    find_unpriced as find_unpriced_core,
)
from gcp_cost_estimator.core.advisory import (
    suggest_cheaper_machine_types as suggest_cheaper_machine_types_core,
)
from gcp_cost_estimator.core.catalog import CATALOG_COVERAGE, CATALOG_DEFAULTS
from gcp_cost_estimator.core.compare import (
    compare_estimates as compare_estimates_core,
)
from gcp_cost_estimator.core.compare import (
    compare_regions as compare_regions_core,
)
from gcp_cost_estimator.core.compare import (
    what_if as what_if_core,
)
from gcp_cost_estimator.core.estimate import Estimate
from gcp_cost_estimator.core.iac.terraform_plan import parse_terraform as parse_terraform_core
from gcp_cost_estimator.core.logging import configure_logging
from gcp_cost_estimator.core.model import Resource, ResourceModel, get_resource_model_schema
from gcp_cost_estimator.core.pricing.cache import get_cache_status as get_cache_status_core
from gcp_cost_estimator.core.pricing.gcp_fetch import (
    refresh_pricing_cache as refresh_pricing_cache_core,
)
from gcp_cost_estimator.core.registries import get_output_renderer
from gcp_cost_estimator.core.service import estimate_infrastructure as estimate_infrastructure_core
from gcp_cost_estimator.core.validate import validate_resource_model as validate_resource_model_core

mcp = FastMCP("GCP Cost Estimator")


logger = logging.getLogger("gcp_cost_estimator")


def timed_tool[F: Callable[..., Any]](func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        status = "success"
        try:
            return func(*args, **kwargs)
        except Exception:
            status = "failed"
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000.0
            logger.info(
                "MCP Tool Executed: tool=%s status=%s duration_ms=%.2f",
                func.__name__,
                status,
                duration,
            )

    return wrapper  # type: ignore[return-value]


def get_default_db_path() -> str:
    """Resolve the sqlite pricing database path from environment or user home."""
    env_path = os.environ.get("GCP_BILLING_DB_PATH")
    if env_path:
        return env_path
    home_dir = Path.home() / ".gcp-cost-estimator"
    home_dir.mkdir(parents=True, exist_ok=True)
    return str(home_dir / "pricing.sqlite")


# --- Tools ---


@mcp.tool()
@timed_tool
def parse_terraform(path: str, mode: str = "auto") -> ResourceModel:
    """Parse static HCL files or a Terraform plan JSON to extract ResourceModel."""
    return parse_terraform_core(path, mode=mode)


@mcp.tool()
@timed_tool
def validate_resource_model(model: ResourceModel) -> dict[str, Any]:
    """Validate the canonical resource model, checking for correctness."""
    return validate_resource_model_core(model)


@mcp.tool()
@timed_tool
def estimate_infrastructure(model: ResourceModel) -> Estimate:
    """Estimate the cost of infrastructure specified in the ResourceModel."""
    return estimate_infrastructure_core(get_default_db_path(), model)


@mcp.tool()
@timed_tool
def render_estimate(estimate: Estimate, format: str) -> str:  # noqa: A002
    """Render an Estimate in json, csv, or markdown format."""
    renderer = get_output_renderer(format)
    return renderer.render(estimate)


@mcp.tool()
@timed_tool
def get_cache_status(provider: str = "gcp") -> dict[str, Any]:
    """Get the status and metadata of the local pricing cache."""
    return get_cache_status_core(get_default_db_path(), provider)


@mcp.tool()
@timed_tool
def refresh_pricing_cache(provider: str = "gcp", force: bool = False) -> dict[str, Any]:  # noqa: ARG001
    """Refresh the local pricing cache from public APIs if stale (older than 72 hours)."""
    return refresh_pricing_cache_core(get_default_db_path(), force=force)


@mcp.tool()
@timed_tool
def compare_regions(model: ResourceModel, regions: list[str]) -> dict[str, Any]:
    """Reprice the given resource model across multiple regions and identify the cheapest."""
    return compare_regions_core(get_default_db_path(), model, regions)


@mcp.tool()
@timed_tool
def compare_estimates(estimate_a: Estimate, estimate_b: Estimate) -> dict[str, Any]:
    """Perform a line-item and monthly total difference calculation between two estimates."""
    return compare_estimates_core(estimate_a, estimate_b)


@mcp.tool()
@timed_tool
def what_if(model: ResourceModel, changes: dict[str, Any]) -> dict[str, Any]:
    """Simulate cost modifications by modifying resources and pricing the result."""
    return what_if_core(get_default_db_path(), model, changes)


@mcp.tool()
@timed_tool
def suggest_cheaper_machine_types(resource: Resource) -> list[dict[str, Any]]:
    """Search for cheaper viable VM machine configurations matching or exceeding specs."""
    return suggest_cheaper_machine_types_core(get_default_db_path(), resource)


@mcp.tool()
@timed_tool
def find_unpriced(model: ResourceModel) -> list[dict[str, Any]]:
    """Scan the resource model to identify support/mapping coverage gaps."""
    return find_unpriced_core(get_default_db_path(), model)


# --- Resources ---


@mcp.resource("schema://resource-model")
def get_resource_model_schema_resource() -> str:
    """JSON Schema for the canonical resource model."""
    import json

    return json.dumps(get_resource_model_schema())


@mcp.resource("catalog://coverage")
def get_coverage_resource() -> str:
    """Coverage matrix: GCP services and resource kinds supported in v1."""
    return json.dumps(CATALOG_COVERAGE)


@mcp.resource("catalog://defaults")
def get_defaults_resource() -> str:
    """Default assumptions catalog (e.g. standard runtime hours)."""
    return json.dumps(CATALOG_DEFAULTS)


@mcp.resource("pricing://snapshot")
def get_pricing_snapshot_resource() -> str:
    """Current cache metadata (timestamp, age, SKU counts)."""
    import json

    try:
        status = get_cache_status_core(get_default_db_path(), "gcp")
        return json.dumps(status)
    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve pricing cache status: {e}"})


@mcp.resource("docs://disclaimer")
def get_disclaimer_resource() -> str:
    """Standing cost disclaimer."""
    return "List price only. SUD/CUD/negotiated discounts NOT applied."


# --- Prompts ---


@mcp.prompt("estimate-from-description")
def estimate_from_description(description: str = "") -> str:
    """Guide the LLM to extract a canonical resource model and estimate cost."""
    desc_str = f"description: '{description}'" if description else "no description provided yet"
    return (
        "You are a GCP Cost Estimation Assistant.\n"
        f"The user has provided the following {desc_str}.\n\n"
        "Please perform these steps:\n"
        "1. Retrieve the schema of the canonical resource model from 'schema://resource-model'.\n"
        "2. Parse and map the description into the canonical model.\n"
        "3. Validate the model using 'validate_resource_model'.\n"
        "4. Calculate the cost estimate using 'estimate_infrastructure'.\n"
        "5. Render the final cost breakdown into Markdown table format using 'render_estimate'.\n"
    )


@mcp.prompt("estimate-from-terraform")
def estimate_from_terraform(path: str = "") -> str:
    """Guide the LLM to parse a Terraform directory/plan and estimate cost."""
    path_str = f"located at: '{path}'" if path else "in the current directory or workspace"
    return (
        "You are a GCP Cost Estimation Assistant.\n"
        f"The user wants to analyze the Terraform files {path_str}.\n\n"
        "Please perform these steps:\n"
        "1. Run 'parse_terraform' with the path.\n"
        "2. Call 'estimate_infrastructure' on the resulting ResourceModel.\n"
        "3. Render the cost estimate in markdown format using "
        "'render_estimate' with format='markdown'.\n"
    )


@mcp.prompt("explain-estimate")
def explain_estimate(estimate_json: str = "") -> str:
    """Explain a JSON cost estimate, highlighting main cost drivers and assumptions."""
    estimate_str = estimate_json if estimate_json else "<JSON payload goes here>"
    return (
        "Please explain and analyze this cost estimate payload:\n"
        f"{estimate_str}\n\n"
        "Highlight the primary cost drivers, monthly total, any unpriced/unsupported resources, "
        "and list all assumptions made during the calculation.\n"
    )


@mcp.prompt("optimize-cost")
def optimize_cost(model_or_estimate: str = "") -> str:
    """Provide cost optimization suggestions based on the resources or estimate."""
    content_str = (
        model_or_estimate
        if model_or_estimate
        else "<Infrastructure model or cost estimate payload goes here>"
    )
    return (
        "Based on this infrastructure specification or cost estimate:\n"
        f"{content_str}\n\n"
        "Recommend options for reducing costs (e.g. using cheaper machine types or standard disks "
        "if SSD is not needed), noting that the pricing reflects list prices only.\n"
    )


if __name__ == "__main__":
    configure_logging()
    mcp.run()
