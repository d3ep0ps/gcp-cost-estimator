# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_gcs_bucket(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    sclass = resource.attributes.get("storage_class", "STANDARD").upper()

    size_gb = float(resource.usage.get("size_gb", 0))
    monthly_class_a_ops = float(resource.usage.get("monthly_class_a_ops", 0))
    monthly_class_b_ops = float(resource.usage.get("monthly_class_b_ops", 0))
    monthly_egress_gb = float(resource.usage.get("monthly_egress_gb", 0))
    monthly_retrieval_gb = float(resource.usage.get("monthly_retrieval_gb", 0))

    if sclass not in {"STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"}:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Unsupported storage class '{sclass}' for GCS bucket",
            }
        )
        return mappings, unpriced

    # 1. Emit storage SKU if size_gb > 0
    if size_gb > 0:
        sku_group = f"{sclass.capitalize()}Storage"
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = ?
            """,
            (region, sku_group),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "storage",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": size_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        f"No matching GCS storage SKU found for '{sclass}' in region '{region}'"
                    ),
                }
            )

    # 2. Emit Class A ops SKU if monthly_class_a_ops > 0
    if monthly_class_a_ops > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'StorageOperations'
            AND (description LIKE '%Class A%' OR description LIKE '%class a%')
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "class_a_ops",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": (monthly_class_a_ops / 10000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching Class A operations SKU found in region '{region}'",
                }
            )

    # 3. Emit Class B ops SKU if monthly_class_b_ops > 0
    if monthly_class_b_ops > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'StorageOperations'
            AND (description LIKE '%Class B%' OR description LIKE '%class b%')
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "class_b_ops",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": (monthly_class_b_ops / 10000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching Class B operations SKU found in region '{region}'",
                }
            )

    # 4. Emit egress SKU if monthly_egress_gb > 0
    if monthly_egress_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'Egress'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "egress",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": monthly_egress_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching egress SKU found in region '{region}'",
                }
            )

    # 5. Emit retrieval fee SKU if monthly_retrieval_gb > 0 and storage class is cold
    if monthly_retrieval_gb > 0 and sclass in {"NEARLINE", "COLDLINE", "ARCHIVE"}:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'StorageRetrieval'
            AND (description LIKE ? OR description LIKE ?)
            """,
            (region, f"%{sclass.capitalize()}%", f"%{sclass.lower()}%"),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "retrieval",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": monthly_retrieval_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        f"No matching retrieval SKU found for '{sclass}' in region '{region}'"
                    ),
                }
            )

    return mappings, unpriced
