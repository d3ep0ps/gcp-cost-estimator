# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_spanner_instance(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    edition = resource.attributes.get("edition", "STANDARD").upper()
    config_type = resource.attributes.get("config_type", "regional")
    processing_units = float(resource.attributes.get("processing_units", 100))
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))
    storage_gb = float(resource.usage.get("storage_gb", 0))
    monthly_egress_gb = float(resource.usage.get("monthly_egress_gb", 0))

    edition_display_map = {
        "STANDARD": "Standard",
        "ENTERPRISE": "Enterprise",
        "ENTERPRISE_PLUS": "Enterprise Plus",
    }
    edition_display = edition_display_map.get(edition, "Standard")
    config_display = "Regional" if config_type == "regional" else "Multi-Region"
    desc_pattern = f"Cloud Spanner {edition_display}: {config_display} Processing Unit"

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description = ?
        """,
        (region, desc_pattern),
    )
    compute_rows = cursor.fetchall()
    if compute_rows:
        comp_match = compute_rows[0]
        qty = processing_units * runtime_hours * resource.quantity
        mappings.append(
            {
                "sku_id": comp_match[0],
                "component": "compute",
                "unit": comp_match[1],
                "unit_price": comp_match[2],
                "qty": qty,
            }
        )
    else:
        reason_msg = (
            f"No Cloud Spanner compute SKU found for edition '{edition}' "
            f"config_type '{config_type}' in region '{region}'"
        )
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": reason_msg,
            }
        )

    if storage_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Spanner%Storage%'
            """,
            (region,),
        )
        storage_rows = cursor.fetchall()
        if storage_rows:
            stor_match = storage_rows[0]
            mult = 1
            config = resource.attributes.get("config")
            if config:
                config_str = str(config).lower()
                if config_str.startswith("regional-"):
                    mult = 1
                elif config_str in {"nam4", "eur4"}:
                    mult = 2
                else:
                    mult = 3
            qty = storage_gb * mult * resource.quantity
            mappings.append(
                {
                    "sku_id": stor_match[0],
                    "component": "storage",
                    "unit": stor_match[1],
                    "unit_price": stor_match[2],
                    "qty": qty,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Cloud Spanner storage SKU found in region '{region}'",
                }
            )

    if monthly_egress_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Spanner%Egress%'
            """,
            (region,),
        )
        egress_rows = cursor.fetchall()
        if egress_rows:
            eg_match = egress_rows[0]
            qty = monthly_egress_gb * resource.quantity
            mappings.append(
                {
                    "sku_id": eg_match[0],
                    "component": "egress",
                    "unit": eg_match[1],
                    "unit_price": eg_match[2],
                    "qty": qty,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Cloud Spanner egress SKU found in region '{region}'",
                }
            )

    return mappings, unpriced
