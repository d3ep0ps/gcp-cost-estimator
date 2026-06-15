# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.calc import calculate_line_items, calculate_totals
from gcp_cost_estimator.core.estimate import Estimate, PricedLineItem, UnpricedItem
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.pricing.cache import get_cache_status
from gcp_cost_estimator.core.registries import get_sku_mapper
from gcp_cost_estimator.core.validate import normalize_resource_model, validate_resource_model


def estimate_infrastructure(
    db_path: str, resource_model: ResourceModel, _options: dict[str, Any] | None = None
) -> Estimate:
    """Orchestrate the end-to-end estimation flow.

    Validates the input model, decomposes resources into billing SKUs,
    calculates monthly line items and totals, and aggregates unpriced logs/assumptions.
    """
    # 1. Validate the resource model
    val_res = validate_resource_model(resource_model)

    line_items: list[PricedLineItem] = []
    unpriced_items: list[UnpricedItem] = []
    all_assumptions: list[str] = []

    # Record any validation warnings in assumptions
    for warning in val_res["warnings"]:
        all_assumptions.append(f"Validation Warning: {warning}")

    # Use the normalized model
    normalized_model = val_res.get("normalized_model")
    if not normalized_model:
        # Fallback to normalizer directly to attempt calculation on best-effort basis
        normalized_model = normalize_resource_model(resource_model)

    # 2. Process validation errors if invalid
    if not val_res["valid"]:
        for err in val_res["errors"]:
            # Check which resource might have caused the error (best-effort match)
            matched = False
            for r in normalized_model.resources:
                if r.resource_id in err or r.kind in err:
                    unpriced_items.append(UnpricedItem(resource_id=r.resource_id, reason=err))
                    matched = True
                    break
            if not matched:
                unpriced_items.append(UnpricedItem(resource_id="model", reason=err))
    else:
        # 3. Map and calculate valid resources
        for r in normalized_model.resources:
            # Gather resource-level assumptions (e.g. defaulted runtime)
            all_assumptions.extend(r.assumptions)

            # Check if this resource has a specific validation-level unpriced reason
            val_unpriced_reason = None
            for item in val_res.get("unpriced", []):
                if item["resource_id"] == r.resource_id:
                    val_unpriced_reason = item["reason"]
                    break

            if val_unpriced_reason:
                unpriced_items.append(
                    UnpricedItem(resource_id=r.resource_id, reason=val_unpriced_reason)
                )
                continue

            try:
                # Resolve mapper for the resource provider
                mapper = get_sku_mapper(r.provider, db_path)
                mappings, unpriced = mapper.map_resource_to_skus(r)

                # Capture unpriced components
                for up in unpriced:
                    unpriced_items.append(
                        UnpricedItem(resource_id=r.resource_id, reason=up["reason"])
                    )

                # Perform cost calculations
                resource_line_items = calculate_line_items(r.resource_id, mappings, r.usage)
                line_items.extend(resource_line_items)
            except Exception as e:
                unpriced_items.append(UnpricedItem(resource_id=r.resource_id, reason=str(e)))

    # 4. Resolve snapshot timestamp from cache metadata
    try:
        # GCP is standard provider for v1; fallback to first provider if multiple
        provider = "gcp"
        if normalized_model.resources:
            provider = normalized_model.resources[0].provider

        status = get_cache_status(db_path, provider)
        snapshot_ts = status["last_refreshed_at"] or "unknown"
        if status.get("stale"):
            all_assumptions.append(
                f"Pricing cache is stale (last refreshed at {snapshot_ts}). Please refresh."
            )
    except Exception:
        snapshot_ts = "unknown"

    # 5. Compute total and compile final Estimate
    monthly_total = calculate_totals(line_items)

    # Keep unique assumptions to avoid clutter
    unique_assumptions = sorted(set(all_assumptions))

    return Estimate(
        pricing_snapshot=snapshot_ts,
        line_items=line_items,
        monthly_total=monthly_total,
        unpriced=unpriced_items,
        assumptions=unique_assumptions,
    )
