# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_app_engine_standard_version(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []
    region = resource.region
    if not region:
        return mappings, unpriced

    iclass = resource.attributes.get("instance_class", "F1")
    iclass_upper = iclass.upper()

    multipliers = {
        "F1": 1,
        "F2": 2,
        "F4": 4,
        "F4_1G": 6,
        "B1": 1,
        "B2": 2,
        "B4": 4,
        "B4_1G": 6,
        "B8": 8,
    }
    if iclass_upper not in multipliers:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Unknown instance class '{iclass}' for App Engine standard",
            }
        )
        return mappings, unpriced

    multiplier = multipliers[iclass_upper]
    if iclass_upper.startswith("F"):
        sku_group = "Standard Frontend Instances"
    else:
        sku_group = "Standard Backend Instances"

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND service = 'app engine' AND sku_group = ?
        """,
        (region, sku_group),
    )
    rows = cursor.fetchall()
    if not rows:
        # Fallback search matching description
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
              AND (description LIKE ? OR description LIKE ?)
            """,
            (
                region,
                f"%{sku_group}%",
                f"%{'Frontend' if iclass_upper.startswith('F') else 'Backend'}%",
            ),
        )
        rows = cursor.fetchall()

    if not rows:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (
                    f"No pricing SKU found for App Engine standard "
                    f"{iclass_upper} in region '{region}'"
                ),
            }
        )
    else:
        row = rows[0]
        # Accrual rule: instance-hours continue accruing for 15 minutes
        # (+0.25h) tail per lifecycle event
        lifecycle_events = float(resource.usage.get("lifecycle_events_per_month", 0))
        hours = float(resource.usage.get("runtime_hours_per_month", 730.0))
        total_hours = hours + (lifecycle_events * 0.25)
        qty = total_hours * multiplier * resource.quantity

        mappings.append(
            {
                "sku_id": row[0],
                "component": "instances",
                "unit": row[1],
                "unit_price": row[2],
                "qty": qty,
            }
        )

    # Handle standard egress
    egress_gb = float(resource.usage.get("egress_gb", 0))
    if egress_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'Egress'
            """,
            (region,),
        )
        egress_rows = cursor.fetchall()

        if egress_rows:
            mappings.append(
                {
                    "sku_id": egress_rows[0][0],
                    "component": "egress",
                    "unit": egress_rows[0][1],
                    "unit_price": egress_rows[0][2],
                    "qty": egress_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (f"No egress SKU found for App Engine standard in region '{region}'"),
                }
            )

    return mappings, unpriced


def map_app_engine_flexible_version(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []
    region = resource.region
    if not region:
        return mappings, unpriced

    cpu = int(resource.attributes.get("cpu", 1))
    memory_gb = float(resource.attributes.get("memory_gb", 3.75))

    # vCPU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
          AND sku_group = 'Flexible CPU'
        """,
        (region,),
    )
    cpu_rows = cursor.fetchall()
    if not cpu_rows:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
              AND (description LIKE '%Flexible%CPU%' OR description LIKE '%Flexible%vCPU%')
            """,
            (region,),
        )
        cpu_rows = cursor.fetchall()

    if cpu_rows:
        mappings.append(
            {
                "sku_id": cpu_rows[0][0],
                "component": "vcpu",
                "unit": cpu_rows[0][1],
                "unit_price": cpu_rows[0][2],
                "qty": float(cpu) * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No Flexible CPU SKU found for App Engine in region '{region}'",
            }
        )

    # RAM
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
          AND sku_group = 'Flexible RAM'
        """,
        (region,),
    )
    ram_rows = cursor.fetchall()
    if not ram_rows:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
              AND (description LIKE '%Flexible%RAM%' OR description LIKE '%Flexible%Memory%')
            """,
            (region,),
        )
        ram_rows = cursor.fetchall()

    if ram_rows:
        mappings.append(
            {
                "sku_id": ram_rows[0][0],
                "component": "ram",
                "unit": ram_rows[0][1],
                "unit_price": ram_rows[0][2],
                "qty": memory_gb * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No Flexible RAM SKU found for App Engine in region '{region}'",
            }
        )

    # Process attached resources (like disks)
    for attached in resource.attached:
        if "disk" in attached.kind.lower():
            sku_group = "SSD" if "ssd" in attached.kind.lower() else "PDStandard"
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = ?
                """,
                (region, sku_group),
            )
            disk_rows = cursor.fetchall()
            if disk_rows:
                disk_match = disk_rows[0]
                size_gb = float(attached.attributes.get("size_gb", 0))
                mappings.append(
                    {
                        "sku_id": disk_match[0],
                        "component": "storage",
                        "unit": disk_match[1],
                        "unit_price": disk_match[2],
                        "qty": size_gb * attached.quantity * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": f"{resource.resource_id}/{attached.kind}",
                        "reason": (
                            f"No matching storage SKU found for '{attached.kind}' "
                            f"in region {region}"
                        ),
                    }
                )
        else:
            unpriced.append(
                {
                    "resource_id": f"{resource.resource_id}/{attached.kind}",
                    "reason": f"Unsupported attached resource kind '{attached.kind}'",
                }
            )

    # Egress
    egress_gb = float(resource.usage.get("egress_gb", 0))
    if egress_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'Egress'
            """,
            (region,),
        )
        egress_rows = cursor.fetchall()
        if egress_rows:
            mappings.append(
                {
                    "sku_id": egress_rows[0][0],
                    "component": "egress",
                    "unit": egress_rows[0][1],
                    "unit_price": egress_rows[0][2],
                    "qty": egress_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No egress SKU found in region '{region}'",
                }
            )

    return mappings, unpriced
