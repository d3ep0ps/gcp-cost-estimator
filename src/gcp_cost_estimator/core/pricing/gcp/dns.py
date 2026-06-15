# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_dns_managed_zone(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))
    monthly_queries = float(resource.usage.get("monthly_queries", 0))

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'DnsZones'
        """
    )
    row = cursor.fetchone()
    if row:
        mappings.append(
            {
                "sku_id": row[0],
                "component": "managed_zones",
                "unit": row[1],
                "unit_price": row[2],
                "qty": (runtime_hours / 730.0) * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "No matching SKU found for Cloud DNS Managed Zones",
            }
        )

    if monthly_queries > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'DnsQueries'
            """
        )
        row = cursor.fetchone()
        if row:
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "dns_queries",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": (monthly_queries / 1000000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "No matching SKU found for Cloud DNS Queries",
                }
            )

    return mappings, unpriced
