# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.estimate import Estimate
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.service import estimate_infrastructure


def compare_regions(db_path: str, model: ResourceModel, regions: list[str]) -> dict[str, Any]:
    """Reprice the given resource model across multiple regions and identify the cheapest."""
    estimates: dict[str, Estimate] = {}
    for r in regions:
        # Create a deep copy of the model and override all resource regions
        model_copy = model.model_copy(deep=True)
        for res in model_copy.resources:
            res.region = r
        estimates[r] = estimate_infrastructure(db_path, model_copy)

    # Find the cheapest region based on monthly total cost
    cheapest_region = None
    min_cost = float("inf")
    for region, est in estimates.items():
        if est.monthly_total < min_cost:
            min_cost = est.monthly_total
            cheapest_region = region

    return {
        "cheapest_region": cheapest_region,
        "estimates": estimates,
    }


def compare_estimates(a: Estimate, b: Estimate) -> dict[str, Any]:
    """Perform a line-item and monthly total difference calculation between two estimates."""
    total_diff = b.monthly_total - a.monthly_total

    # Index line items by (resource_id, component, sku_id)
    items_a = {(item.resource_id, item.component, item.sku_id): item for item in a.line_items}
    items_b = {(item.resource_id, item.component, item.sku_id): item for item in b.line_items}

    diffs: list[dict[str, Any]] = []
    all_keys = set(items_a.keys()) | set(items_b.keys())

    for key in sorted(all_keys):
        res_id, comp, sku = key
        item_a = items_a.get(key)
        item_b = items_b.get(key)

        cost_a = item_a.monthly_cost if item_a else 0.0
        cost_b = item_b.monthly_cost if item_b else 0.0
        cost_diff = cost_b - cost_a

        qty_a = item_a.qty if item_a else 0.0
        qty_b = item_b.qty if item_b else 0.0
        qty_diff = qty_b - qty_a

        diffs.append(
            {
                "resource_id": res_id,
                "component": comp,
                "sku_id": sku,
                "cost_a": cost_a,
                "cost_b": cost_b,
                "cost_diff": cost_diff,
                "qty_a": qty_a,
                "qty_b": qty_b,
                "qty_diff": qty_diff,
            }
        )

    return {
        "monthly_total_a": a.monthly_total,
        "monthly_total_b": b.monthly_total,
        "monthly_total_diff": total_diff,
        "line_item_diffs": diffs,
    }


def what_if(db_path: str, model: ResourceModel, changes: dict[str, Any]) -> dict[str, Any]:
    """Simulate cost modifications by modifying resources and pricing the result."""
    original_est = estimate_infrastructure(db_path, model)

    model_copy = model.model_copy(deep=True)
    for r in model_copy.resources:
        # Apply global changes
        if "region" in changes:
            r.region = changes["region"]
        if "runtime_hours" in changes:
            r.usage["runtime_hours_per_month"] = changes["runtime_hours"]
        if (
            "machine_type" in changes
            and r.provider == "gcp"
            and r.service == "compute"
            and r.kind == "gce_instance"
        ):
            r.attributes["machine_type"] = changes["machine_type"]

        # Apply resource-specific changes
        res_changes = changes.get("resources", {}).get(r.resource_id, {})
        if "region" in res_changes:
            r.region = res_changes["region"]
        if "runtime_hours" in res_changes:
            r.usage["runtime_hours_per_month"] = res_changes["runtime_hours"]
        if "machine_type" in res_changes:
            r.attributes["machine_type"] = res_changes["machine_type"]

    new_est = estimate_infrastructure(db_path, model_copy)
    comparison = compare_estimates(original_est, new_est)

    return {
        "new_estimate": new_est,
        "comparison": comparison,
    }
