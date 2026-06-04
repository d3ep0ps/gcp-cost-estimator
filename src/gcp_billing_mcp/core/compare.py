# SPDX-License-Identifier: Apache-2.0

import re
import sqlite3
from typing import Any

from gcp_billing_mcp.core.estimate import Estimate
from gcp_billing_mcp.core.model import Resource, ResourceModel
from gcp_billing_mcp.core.pricing.gcp import resolve_machine_type_specs, resolve_sql_tier_specs
from gcp_billing_mcp.core.registries import get_sku_mapper
from gcp_billing_mcp.core.service import estimate_infrastructure

# Standard vCPU counts to probe for suggestions (covers the vast majority of real workloads).
_CANDIDATE_VCPU_COUNTS = [1, 2, 4, 8, 16, 32, 48, 64, 96]
_CANDIDATE_SUBTYPES = ["standard", "highmem", "highcpu"]

# Map family prefix (uppercase, from SKU description) → lowercase family name in machine type.
_FAMILY_PREFIX_TO_NAME_RE = re.compile(r"^([A-Z][A-Z0-9]+)\b")


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


def suggest_cheaper_machine_types(db_path: str, resource: Resource) -> list[dict[str, Any]]:
    """Search for cheaper viable VM machine configurations matching or exceeding specs.

    Candidate machine types are derived from the SKU cache (CPU SKU descriptions in the
    resource's region), so the function automatically includes any machine family Google
    adds after this code was written — no code change required.
    """
    if resource.provider != "gcp":
        return []

    if resource.service == "compute" and resource.kind == "gce_instance":
        mtype = resource.attributes.get("machine_type", "")
        current_vcpu, current_ram = resolve_machine_type_specs(mtype)
        if current_vcpu == 0:
            return []

        # Price current instance to establish a baseline
        current_model = ResourceModel(resources=[resource])
        current_est = estimate_infrastructure(db_path, current_model)
        current_cost = current_est.monthly_total

        # Build candidate list from families present in the cache for this region.
        region = resource.region or ""
        families: set[str] = set()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT description FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'CPU'
                """,
                (region,),
            )
            for (desc,) in cursor.fetchall():
                m = _FAMILY_PREFIX_TO_NAME_RE.match(desc.strip())
                if m:
                    families.add(m.group(1).lower())
        finally:
            conn.close()

        suggestions: list[dict[str, Any]] = []

        for family in sorted(families):
            for subtype in _CANDIDATE_SUBTYPES:
                for n_vcpu in _CANDIDATE_VCPU_COUNTS:
                    name = f"{family}-{subtype}-{n_vcpu}"
                    if name == mtype:
                        continue
                    cand_vcpu, cand_ram = resolve_machine_type_specs(name)
                    if cand_vcpu == 0:
                        continue
                    # Must match or exceed both the vCPU count and RAM requirement.
                    if cand_vcpu >= current_vcpu and cand_ram >= current_ram:
                        candidate_resource = resource.model_copy(deep=True)
                        candidate_resource.attributes["machine_type"] = name
                        candidate_model = ResourceModel(resources=[candidate_resource])
                        candidate_est = estimate_infrastructure(db_path, candidate_model)
                        candidate_cost = candidate_est.monthly_total

                        if candidate_cost < current_cost:
                            suggestions.append(
                                {
                                    "machine_type": name,
                                    "vcpu": cand_vcpu,
                                    "ram_gb": cand_ram,
                                    "monthly_cost": candidate_cost,
                                    "monthly_savings": current_cost - candidate_cost,
                                }
                            )

        # Sort suggestions by cost (cheapest configuration first)
        suggestions.sort(key=lambda x: x["monthly_cost"])
        return suggestions

    if resource.service == "sql" and resource.kind == "cloud_sql_instance":
        tier = resource.attributes.get("tier", "")
        current_vcpu, current_ram = resolve_sql_tier_specs(tier)
        if current_vcpu == 0:
            return []

        # Price current instance to establish a baseline
        current_model = ResourceModel(resources=[resource])
        current_est = estimate_infrastructure(db_path, current_model)
        current_cost = current_est.monthly_total

        suggestions = []

        # Generate candidate custom tiers: db-custom-N-M
        # N: vCPU count, M: RAM in MB
        for cand_vcpu in _CANDIDATE_VCPU_COUNTS:
            if cand_vcpu >= current_vcpu:
                # RAM per vCPU must be between 0.9 GB and 6.5 GB.
                min_ram_gb = max(current_ram, 0.9 * cand_vcpu)
                max_ram_gb = 6.5 * cand_vcpu
                if min_ram_gb <= max_ram_gb:
                    ram_options = [min_ram_gb]
                    for r in [3.75 * cand_vcpu, 6.5 * cand_vcpu]:
                        if r >= current_ram and 0.9 * cand_vcpu <= r <= 6.5 * cand_vcpu:
                            ram_options.append(r)

                    # Deduplicate and round to nearest 256MB multiple
                    seen_mb = set()
                    for ram_gb in ram_options:
                        ram_mb = int(round(ram_gb * 1024 / 256.0) * 256)
                        if ram_mb not in seen_mb:
                            seen_mb.add(ram_mb)
                            cand_ram_gb = ram_mb / 1024.0

                            # Double check constraints
                            if cand_vcpu >= current_vcpu and cand_ram_gb >= current_ram:
                                name = f"db-custom-{cand_vcpu}-{ram_mb}"
                                if name == tier:
                                    continue

                                candidate_resource = resource.model_copy(deep=True)
                                candidate_resource.attributes["tier"] = name
                                candidate_model = ResourceModel(resources=[candidate_resource])
                                candidate_est = estimate_infrastructure(db_path, candidate_model)
                                candidate_cost = candidate_est.monthly_total

                                if candidate_cost < current_cost:
                                    suggestions.append(
                                        {
                                            "tier": name,
                                            "machine_type": name,  # For backward compatibility
                                            "vcpu": cand_vcpu,
                                            "ram_gb": cand_ram_gb,
                                            "monthly_cost": candidate_cost,
                                            "monthly_savings": current_cost - candidate_cost,
                                        }
                                    )

        # Sort suggestions by cost (cheapest configuration first)
        suggestions.sort(key=lambda x: x["monthly_cost"])
        return suggestions

    if resource.service == "bigquery" and resource.kind == "bigquery_dataset":
        active_gb = float(resource.usage.get("active_storage_gb", 0))
        if active_gb > 0:
            region = resource.region or "us"
            active_price = 0.02
            long_term_price = 0.01

            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT unit_price FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
                    AND (description LIKE '%Active%')
                    """,
                    (region,),
                )
                row = cursor.fetchone()
                if row:
                    active_price = row[0]

                cursor.execute(
                    """
                    SELECT unit_price FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
                    AND (description LIKE '%Long Term%')
                    """,
                    (region,),
                )
                row = cursor.fetchone()
                if row:
                    long_term_price = row[0]
            finally:
                conn.close()

            current_cost = active_gb * active_price
            lt_cost = active_gb * long_term_price
            savings = current_cost - lt_cost

            if savings > 0:
                return [
                    {
                        "recommendation": (
                            "Transition unmodified tables/partitions (90+ days) "
                            "to long-term storage to reduce active storage costs."
                        ),
                        "monthly_cost": lt_cost,
                        "monthly_savings": savings,
                    }
                ]
        return []

    return []


def find_unpriced(db_path: str, model: ResourceModel) -> list[dict[str, Any]]:
    """Scan the resource model to identify support/mapping coverage gaps."""
    unpriced_list: list[dict[str, Any]] = []

    for r in model.resources:
        try:
            mapper = get_sku_mapper(r.provider, db_path)
            _, unpriced = mapper.map_resource_to_skus(r)
            for up in unpriced:
                unpriced_list.append(
                    {
                        "resource_id": r.resource_id,
                        "sub_resource_id": up.get("resource_id", r.resource_id),
                        "reason": up["reason"],
                    }
                )
        except Exception as e:
            unpriced_list.append(
                {
                    "resource_id": r.resource_id,
                    "reason": str(e),
                }
            )

    return unpriced_list
