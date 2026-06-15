# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_nat_gateway(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    # Get usage inputs
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))
    num_vms = int(float(resource.usage.get("num_vms", 1)))
    num_nat_ips = int(float(resource.usage.get("num_nat_ips", 1)))
    monthly_data = float(resource.usage.get("monthly_data_processed_gb", 10))

    region = resource.region or "us-central1"

    # 1. Gateway uptime hourly charge: min(num_vms * $0.0014, $0.044) per hour
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'NatGatewayUptime' AND region = ?
        """,
        (region,),
    )
    row = cursor.fetchone()
    if row:
        sku_id, unit, unit_price, desc = row
        hourly_rate_per_vm = float(unit_price)
        if hourly_rate_per_vm > 0:
            effective_vms = min(num_vms, 0.044 / hourly_rate_per_vm)
            qty = effective_vms * runtime_hours * resource.quantity
            mappings.append(
                {
                    "sku_id": sku_id,
                    "component": "gateway_uptime",
                    "unit": unit,
                    "unit_price": unit_price,
                    "qty": qty,
                }
            )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No matching SKU found for Cloud NAT Gateway Uptime in region {region}",
            }
        )

    # 2. Data processed
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'NatDataProcessed' AND region = ?
        """,
        (region,),
    )
    row = cursor.fetchone()
    if row:
        sku_id, unit, unit_price, desc = row
        mappings.append(
            {
                "sku_id": sku_id,
                "component": "data_processed",
                "unit": unit,
                "unit_price": unit_price,
                "qty": monthly_data * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No matching SKU found for Cloud NAT Data Processed in region {region}",
            }
        )

    # 3. NAT IP address uptime (only if num_nat_ips > 0)
    if num_nat_ips > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'NatIpUptime' AND region = ?
            """,
            (region,),
        )
        row = cursor.fetchone()
        if row:
            sku_id, unit, unit_price, _desc = row
            mappings.append(
                {
                    "sku_id": sku_id,
                    "component": "ip_uptime",
                    "unit": unit,
                    "unit_price": unit_price,
                    "qty": num_nat_ips * runtime_hours * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching SKU found for Cloud NAT IP Address Uptime in region {region}",
                }
            )

    return mappings, unpriced
