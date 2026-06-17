# SPDX-License-Identifier: Apache-2.0
"""SKU mapper for Vertex AI inference endpoints.

Pricing source: https://cloud.google.com/vertex-ai/pricing (verified 2026-06-15)
Scope: google_vertex_ai_endpoint only.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource

HOURS_PER_MONTH = 730

# Per-node-hour rates for N1 prediction machines, us-central1
# Source: https://cloud.google.com/vertex-ai/pricing, verified 2026-06-15
_N1_PREDICTION_RATES: dict[str, float] = {
    "n1-standard-2": 0.1095,
    "n1-standard-4": 0.2190,
    "n1-standard-8": 0.4380,
    "n1-standard-16": 0.8760,
    "n1-highmem-2": 0.1370,
    "n1-highmem-4": 0.2740,
    "n1-highmem-8": 0.5480,
}
_DEFAULT_MACHINE_TYPE = "n1-standard-2"
_DEFAULT_NODE_COUNT = 1


def map_vertex_ai_endpoint(
    resource: Resource,
    cursor: sqlite3.Cursor,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map google_vertex_ai_endpoint to SKU line items.

    Returns (mappings, unpriced).
    """
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    attrs = resource.attributes
    dedicated = attrs.get("dedicated_endpoint_enabled", False)

    # Both dedicated and shared endpoints have traffic-dependent inference costs that are unpriced
    unpriced.append({
        "resource_id": resource.resource_id,
        "reason": (
            "Vertex AI inference traffic costs (per-prediction) are not estimable "
            "from Terraform IaC; depends on deployed model and request volume. "
            "Source: https://cloud.google.com/vertex-ai/pricing#prediction-and-explanation"
        ),
    })

    if not dedicated:
        unpriced.insert(0, {
            "resource_id": resource.resource_id,
            "reason": (
                "Vertex AI shared endpoint: no idle infrastructure cost. "
                "Inference billed per request based on deployed model machine type (not in IaC)."
            ),
        })
        return mappings, unpriced

    # Dedicated endpoint: compute node hours cost
    machine_type = attrs.get("machine_type", _DEFAULT_MACHINE_TYPE)
    node_count = int(attrs.get("node_count", _DEFAULT_NODE_COUNT))
    hours = float(resource.usage.get("runtime_hours_per_month", HOURS_PER_MONTH))

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE ?
        """,
        (region, f"%Vertex AI%Prediction%{machine_type}%"),
    )
    rows = cursor.fetchall()

    if rows:
        sku_id, unit, unit_price = rows[0]
    else:
        sku_id = f"SKU-VERTEXAI-PREDICTION-{machine_type.upper()}"
        unit = "node-hour"
        unit_price = _N1_PREDICTION_RATES.get(machine_type, _N1_PREDICTION_RATES[_DEFAULT_MACHINE_TYPE])

    qty = node_count * hours * resource.quantity
    mappings.append({
        "sku_id": sku_id,
        "component": "compute",
        "unit": unit,
        "unit_price": unit_price,
        "qty": qty,
    })

    return mappings, unpriced
