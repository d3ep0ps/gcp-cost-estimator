# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_compute_address(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    # Get address type (default to EXTERNAL)
    addr_type = resource.attributes.get("address_type", "EXTERNAL").upper()
    if addr_type == "INTERNAL":
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "Internal IP addresses are free",
            }
        )
        return mappings, unpriced

    # Extract usage values
    in_use = resource.usage.get("in_use", True)
    in_use = in_use.lower() in {"true", "1", "yes"} if isinstance(in_use, str) else bool(in_use)

    on_spot_vm = resource.usage.get("on_spot_vm", False)
    if isinstance(on_spot_vm, str):
        on_spot_vm = on_spot_vm.lower() in {"true", "1", "yes"}
    else:
        on_spot_vm = bool(on_spot_vm)

    on_forwarding_rule = resource.usage.get("on_forwarding_rule", False)
    if isinstance(on_forwarding_rule, str):
        on_forwarding_rule = on_forwarding_rule.lower() in {"true", "1", "yes"}
    else:
        on_forwarding_rule = bool(on_forwarding_rule)

    # If it is attached to a forwarding rule or VPN tunnel, there is no charge.
    if on_forwarding_rule:
        return mappings, unpriced

    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730))
    region = resource.region or "us-central1"

    # Select the appropriate SKU group based on in_use, spot, etc.
    if not in_use:
        sku_group = "VpcStaticIpUnused"
        component = "static_ip"
    else:
        if on_spot_vm:
            sku_group = "VpcStaticIpInUseSpot"
            component = "static_ip"
        else:
            sku_group = "VpcStaticIpInUse"
            component = "static_ip"

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = ? AND region = ?
        """,
        (sku_group, region),
    )
    row = cursor.fetchone()
    if row:
        sku_id, unit, unit_price, _desc = row
        mappings.append(
            {
                "sku_id": sku_id,
                "component": component,
                "unit": unit,
                "unit_price": unit_price,
                "qty": runtime_hours * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No matching SKU found for VPC Static IP under group {sku_group} in region {region}",
            }
        )

    return mappings, unpriced
