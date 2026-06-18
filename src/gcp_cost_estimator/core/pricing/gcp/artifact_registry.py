# SPDX-License-Identifier: Apache-2.0
"""SKU mapper for google_artifact_registry_repository.

Pricing source: https://cloud.google.com/artifact-registry/pricing (verified 2026-06-15)
Storage: $0.10/GB/month over 0.5 GB free tier.
Data transfer: free within same region; US/Canada cross-region is $0.01/GB.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource

_STORAGE_FREE_TIER_GB = 0.5  # first 0.5 GB free per billing account per month
_STORAGE_RATE_PER_GB = 0.10  # $/GB/month, verified 2026-06-15
_CROSS_REGION_RATE_NORTH_AMERICA = 0.01  # $/GB US/Canada cross-region


def map_artifact_registry_repository(
    resource: Resource,
    cursor: sqlite3.Cursor,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map google_artifact_registry_repository to SKU line items."""
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    attrs = resource.attributes
    storage_gb = float(attrs.get("storage_gb", 10.0))
    egress_gb = float(attrs.get("monthly_egress_gb", 0.0))

    # Storage mapping
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE '%Artifact Registry%Storage%'
        """,
        (region,),
    )
    storage_rows = cursor.fetchall()

    if storage_rows:
        sku_id, unit, unit_price = storage_rows[0]
    else:
        sku_id = "SKU-ARTIFACT-REGISTRY-STORAGE"
        unit = "GB-month"
        unit_price = _STORAGE_RATE_PER_GB

    billable_storage = max(0.0, storage_gb - _STORAGE_FREE_TIER_GB)

    # We set quantity to billable_storage to account for the 0.5 GB free tier,
    # since monthly_cost for storage is computed as unit_price * qty in calc.py.
    mappings.append(
        {
            "sku_id": sku_id,
            "component": "storage",
            "unit": unit,
            "unit_price": unit_price,
            "qty": billable_storage * resource.quantity,
        }
    )

    # Egress: only add if non-zero
    if egress_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Artifact Registry%Egress%'
            """,
            (region,),
        )
        egress_rows = cursor.fetchall()

        if egress_rows:
            egress_sku_id, egress_unit, egress_unit_price = egress_rows[0]
        else:
            egress_sku_id = "SKU-ARTIFACT-REGISTRY-EGRESS"
            egress_unit = "GB"
            egress_unit_price = _CROSS_REGION_RATE_NORTH_AMERICA

        mappings.append(
            {
                "sku_id": egress_sku_id,
                "component": "egress",
                "unit": egress_unit,
                "unit_price": egress_unit_price,
                "qty": egress_gb * resource.quantity,
            }
        )

    # Vulnerability scanning is unpriced
    unpriced.append(
        {
            "resource_id": resource.resource_id,
            "reason": (
                "Artifact Registry vulnerability scanning billed separately via Artifact Analysis. "
                "Source: https://cloud.google.com/artifact-analysis/pricing"
            ),
        }
    )

    return mappings, unpriced
