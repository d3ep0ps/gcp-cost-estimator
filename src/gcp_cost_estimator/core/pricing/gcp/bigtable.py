# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_bigtable_instance(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    clusters = resource.attributes.get("clusters")
    if not clusters:
        return mappings, unpriced

    storage_gb_per_cluster = float(resource.usage.get("storage_gb_per_cluster", 0))
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))

    for cl in clusters:
        reg = cl.get("region")
        if not reg:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No region derived for cluster in zone '{cl.get('zone')}'",
                }
            )
            continue

        stype = cl.get("storage_type", "SSD").upper()
        num_nodes = int(cl.get("num_nodes", 3))

        # 1. Node SKU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE ?
            """,
            (reg, f"%Bigtable%{stype}%Node%"),
        )
        node_rows = cursor.fetchall()
        if node_rows:
            row = node_rows[0]
            qty = num_nodes * runtime_hours * resource.quantity
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "compute",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": qty,
                }
            )
        else:
            reason_msg = f"No Bigtable node SKU found for type '{stype}' in region '{reg}'"
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": reason_msg,
                }
            )

        # 2. Storage SKU
        if storage_gb_per_cluster > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND description LIKE ?
                """,
                (reg, f"%Bigtable%{stype}%Storage%"),
            )
            storage_rows = cursor.fetchall()
            if storage_rows:
                row = storage_rows[0]
                qty = storage_gb_per_cluster * resource.quantity
                mappings.append(
                    {
                        "sku_id": row[0],
                        "component": "storage",
                        "unit": row[1],
                        "unit_price": row[2],
                        "qty": qty,
                    }
                )
            else:
                reason_msg = f"No Bigtable storage SKU found for type '{stype}' in region '{reg}'"
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": reason_msg,
                    }
                )

    return mappings, unpriced
