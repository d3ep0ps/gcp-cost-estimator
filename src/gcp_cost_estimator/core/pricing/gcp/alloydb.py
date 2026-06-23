# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.gcp.specs import resolve_alloydb_instance_specs


def map_alloydb_cluster(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []
    region = resource.region

    storage_gb = float(resource.usage.get("storage_gb", 100))
    backup_enabled = bool(resource.usage.get("backup_enabled", False))

    # 1. Storage SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp'
          AND region = ?
          AND description LIKE '%AlloyDB%Storage%'
          AND description NOT LIKE '%Backup%'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if rows:
        row = rows[0]
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
                "reason": f"No AlloyDB storage SKU found in region '{region}'",
            }
        )

    # 2. Backup SKU
    if backup_enabled:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND description LIKE '%AlloyDB%Backup%'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            row = rows[0]
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "backup",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": storage_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No AlloyDB backup SKU found in region '{region}'",
                }
            )

    return mappings, unpriced


def map_alloydb_instance(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []
    region = resource.region

    cpu_count = resource.attributes.get("cpu_count")
    if cpu_count is None:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "Missing cpu_count attribute",
            }
        )
        return mappings, unpriced

    try:
        cpu_val = int(cpu_count)
    except ValueError, TypeError:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Invalid cpu_count attribute: {cpu_count}",
            }
        )
        return mappings, unpriced

    vcpu, ram_gb = resolve_alloydb_instance_specs(cpu_val)
    if vcpu == 0:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Unsupported cpu_count attribute: {cpu_count}",
            }
        )
        return mappings, unpriced

    instance_type = resource.attributes.get("instance_type", "PRIMARY").upper()
    node_count = int(resource.attributes.get("node_count", 1))
    node_multiplier = node_count if instance_type == "READ_POOL" else 1

    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))

    # 1. vCPU SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE '%AlloyDB%vCPU%'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if rows:
        row = rows[0]
        mappings.append(
            {
                "sku_id": row[0],
                "component": "compute_vcpu",
                "unit": row[1],
                "unit_price": row[2],
                "qty": vcpu * node_multiplier * runtime_hours * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No AlloyDB vCPU SKU found in region '{region}'",
            }
        )

    # 2. RAM SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND description LIKE '%AlloyDB%RAM%'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if rows:
        row = rows[0]
        mappings.append(
            {
                "sku_id": row[0],
                "component": "compute_ram",
                "unit": row[1],
                "unit_price": row[2],
                "qty": ram_gb * node_multiplier * runtime_hours * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No AlloyDB RAM SKU found in region '{region}'",
            }
        )

    return mappings, unpriced
