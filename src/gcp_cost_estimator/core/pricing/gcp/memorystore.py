# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_redis_instance(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    tier = resource.attributes.get("tier", "BASIC").upper()
    memory_size_gb = float(resource.attributes.get("memory_size_gb", 0))
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))

    tier_desc = "Basic" if tier == "BASIC" else "Standard"
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE ?
        """,
        (region, f"%Redis%{tier_desc}%Capacity%"),
    )
    rows = cursor.fetchall()
    if rows:
        row = rows[0]
        mappings.append(
            {
                "sku_id": row[0],
                "component": "cache",
                "unit": row[1],
                "unit_price": row[2],
                "qty": memory_size_gb * runtime_hours * resource.quantity,
            }
        )
    else:
        reason_msg = (
            f"No Memorystore Redis capacity SKU found for tier '{tier}' in region '{region}'"
        )
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": reason_msg,
            }
        )

    return mappings, unpriced


def map_memorystore_instance(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    shard_count = int(resource.attributes.get("shard_count", 1))
    node_type = resource.attributes.get("node_type", "")
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))

    node_memory_map = {
        "SHARED_CORE_NANO": 1.0,
        "STANDARD_SMALL": 5.0,
        "HIGHMEM_MEDIUM": 13.0,
        "HIGHMEM_XLARGE": 58.0,
    }
    if node_type not in node_memory_map:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Unknown node_type '{node_type}' for Memorystore Valkey instance",
            }
        )
        return mappings, unpriced

    memory_gb_per_shard = node_memory_map[node_type]
    total_gb = memory_gb_per_shard * shard_count

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE '%Valkey%Capacity%'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if rows:
        row = rows[0]
        mappings.append(
            {
                "sku_id": row[0],
                "component": "cache",
                "unit": row[1],
                "unit_price": row[2],
                "qty": total_gb * runtime_hours * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No Memorystore Valkey capacity SKU found in region '{region}'",
            }
        )

    return mappings, unpriced
