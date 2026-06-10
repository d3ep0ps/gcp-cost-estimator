# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_firestore_database(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    storage_gb = float(resource.usage.get("storage_gb", 1))
    monthly_reads = float(resource.usage.get("monthly_reads", 500000))
    monthly_writes = float(resource.usage.get("monthly_writes", 100000))
    monthly_deletes = float(resource.usage.get("monthly_deletes", 10000))
    monthly_egress_gb = float(resource.usage.get("monthly_egress_gb", 0))

    # 1. Storage SKU
    if storage_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Firestore%Storage%'
            """,
            (region,),
        )
        storage_rows = cursor.fetchall()
        if storage_rows:
            row = storage_rows[0]
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "storage",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": storage_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Firestore storage SKU found in region '{region}'",
                }
            )

    # 2. Reads SKU
    if monthly_reads > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Firestore%Read%'
            """,
            (region,),
        )
        reads_rows = cursor.fetchall()
        if reads_rows:
            row = reads_rows[0]
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "reads",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": (monthly_reads / 100000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Firestore reads SKU found in region '{region}'",
                }
            )

    # 3. Writes SKU
    if monthly_writes > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Firestore%Write%'
            """,
            (region,),
        )
        writes_rows = cursor.fetchall()
        if writes_rows:
            row = writes_rows[0]
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "writes",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": (monthly_writes / 100000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Firestore writes SKU found in region '{region}'",
                }
            )

    # 4. Deletes SKU
    if monthly_deletes > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Firestore%Delete%'
            """,
            (region,),
        )
        deletes_rows = cursor.fetchall()
        if deletes_rows:
            row = deletes_rows[0]
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "deletes",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": (monthly_deletes / 100000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Firestore deletes SKU found in region '{region}'",
                }
            )

    # 5. Egress SKU
    if monthly_egress_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%Firestore%Egress%'
            """,
            (region,),
        )
        egress_rows = cursor.fetchall()
        if egress_rows:
            row = egress_rows[0]
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "egress",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": monthly_egress_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No Firestore egress SKU found in region '{region}'",
                }
            )

    return mappings, unpriced
