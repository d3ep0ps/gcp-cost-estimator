# SPDX-License-Identifier: Apache-2.0
"""SKU mapper for google_filestore_instance.

Pricing source: https://cloud.google.com/filestore/pricing (verified 2026-06-15)
Rates shown are us-central1. The mapper reads actual rates from the SKU cache.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource

HOURS_PER_MONTH = 730

# Fallback rates (us-central1) — verified 2026-06-15 from https://cloud.google.com/filestore/pricing
# Stored as $/GiB-hour; converted to $/GiB-month = rate * HOURS_PER_MONTH
_FALLBACK_GIB_HOUR: dict[str, float] = {
    "BASIC_HDD": 0.000219178,
    "BASIC_SSD": 0.000410959,
    "ZONAL": 0.000342466,
    "REGIONAL": 0.000616438,
    "ENTERPRISE": 0.000616438,  # same rate as REGIONAL
    "HIGH_SCALE_SSD": 0.000342466,  # same rate as ZONAL
}
_BASIC_HDD_INSTANCE_FEE_PER_HOUR = 0.045205479  # waived when capacity >= 1024 GiB


def map_filestore_instance(
    resource: Resource,
    cursor: sqlite3.Cursor,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map google_filestore_instance to SKU line items.

    Returns (mappings, unpriced).
    """
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    attrs = resource.attributes
    tier = str(attrs.get("tier", "BASIC_HDD")).upper()
    capacity_gb = float(attrs.get("capacity_gb", 1024.0))
    hours = float(resource.usage.get("runtime_hours_per_month", HOURS_PER_MONTH))

    tier_desc = tier.replace("_", " ").title()

    # Storage Capacity mapping
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE ?
        """,
        (region, f"%Filestore%{tier_desc}%Capacity%"),
    )
    storage_rows = cursor.fetchall()

    if storage_rows:
        sku_id, unit, unit_price = storage_rows[0]
    else:
        # Fallback to hardcoded values if not found in database cache
        sku_id = f"SKU-FILESTORE-{tier}-CAPACITY"
        unit = "GiB-hour"
        unit_price = _FALLBACK_GIB_HOUR.get(tier, _FALLBACK_GIB_HOUR["ZONAL"])

    # Compute billed quantity in GiB-hours (capacity_gb * runtime_hours)
    qty = capacity_gb * hours * resource.quantity
    mappings.append(
        {
            "sku_id": sku_id,
            "component": "storage",
            "unit": unit,
            "unit_price": unit_price,
            "qty": qty,
        }
    )

    # Basic HDD per-instance charge (waived if capacity >= 1 TiB = 1024 GiB)
    if tier == "BASIC_HDD" and capacity_gb < 1024.0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ?
              AND description LIKE '%Filestore Basic HDD Instance Fee%'
            """,
            (region,),
        )
        fee_rows = cursor.fetchall()

        if fee_rows:
            fee_sku_id, fee_unit, fee_unit_price = fee_rows[0]
        else:
            fee_sku_id = "SKU-FILESTORE-BASIC-HDD-FEE"
            fee_unit = "hour"
            fee_unit_price = _BASIC_HDD_INSTANCE_FEE_PER_HOUR

        # Billed per hour
        fee_qty = hours * resource.quantity
        mappings.append(
            {
                "sku_id": fee_sku_id,
                "component": "compute",
                "unit": fee_unit,
                "unit_price": fee_unit_price,
                "qty": fee_qty,
            }
        )

    # Add backup unpriced detail
    unpriced.append(
        {
            "resource_id": resource.resource_id,
            "reason": "Filestore backup storage pricing not modelled",
        }
    )

    if attrs.get("custom_performance_enabled"):
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "Filestore Custom Performance (provisioned IOPS) pricing not modelled",
            }
        )

    return mappings, unpriced
