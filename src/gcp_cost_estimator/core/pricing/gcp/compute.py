# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.gcp.specs import resolve_machine_type_specs


def map_gce_compute(
    region: str,
    machine_type: str,
    node_count: int,
    disk_size_gb: float,
    disk_type: str,
    resource_quantity: int,
    resource_id: str,
    cursor: sqlite3.Cursor,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    vcpu, ram = resolve_machine_type_specs(machine_type)
    if vcpu == 0:
        unpriced.append(
            {
                "resource_id": resource_id,
                "reason": f"Unknown machine_type '{machine_type}'",
            }
        )
        return mappings, unpriced

    family_prefix = machine_type.split("-")[0].upper()

    # Retrieve CPU SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND sku_group = 'CPU'
        """,
        (region,),
    )
    cpu_rows = cursor.fetchall()
    cpu_match = None
    for row in cpu_rows:
        if family_prefix in row[3].upper():
            cpu_match = row
            break
    if not cpu_match and cpu_rows:
        cpu_match = cpu_rows[0]

    if cpu_match:
        mappings.append(
            {
                "sku_id": cpu_match[0],
                "component": "vcpu",
                "unit": cpu_match[1],
                "unit_price": cpu_match[2],
                "qty": float(vcpu) * node_count * resource_quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource_id,
                "reason": (
                    f"No pricing data for machine family '{family_prefix.lower()}'"
                    f" in region '{region}' — vCPU SKU not found"
                ),
            }
        )

    # Retrieve RAM SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND sku_group = 'RAM'
        """,
        (region,),
    )
    ram_rows = cursor.fetchall()
    ram_match = None
    for row in ram_rows:
        if family_prefix in row[3].upper():
            ram_match = row
            break
    if not ram_match and ram_rows:
        ram_match = ram_rows[0]

    if ram_match:
        mappings.append(
            {
                "sku_id": ram_match[0],
                "component": "ram",
                "unit": ram_match[1],
                "unit_price": ram_match[2],
                "qty": float(ram) * node_count * resource_quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource_id,
                "reason": f"No matching RAM SKU found in region {region}",
            }
        )

    # Disk
    if disk_size_gb > 0:
        sku_group = "SSD" if "ssd" in disk_type.lower() else "PDStandard"
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
            mappings.append(
                {
                    "sku_id": disk_match[0],
                    "component": "storage",
                    "unit": disk_match[1],
                    "unit_price": disk_match[2],
                    "qty": float(disk_size_gb) * node_count * resource_quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource_id,
                    "reason": (
                        f"No matching storage SKU found for '{sku_group}' in region {region}"
                    ),
                }
            )

    return mappings, unpriced


def map_gke_cluster(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced

    # Lookup flat management fee SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ?
        AND (description LIKE '%Kubernetes Engine%' OR description LIKE '%GKE%')
        """,
        (region,),
    )
    mgmt_rows = cursor.fetchall()
    mgmt_match = None
    for row in mgmt_rows:
        if "management fee" in row[3].lower():
            mgmt_match = row
            break
    if not mgmt_match and mgmt_rows:
        mgmt_match = mgmt_rows[0]

    if mgmt_match:
        runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730.0))
        mappings.append(
            {
                "sku_id": mgmt_match[0],
                "component": "management_fee",
                "unit": mgmt_match[1],
                "unit_price": mgmt_match[2],
                "qty": runtime_hours * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No GKE cluster management fee SKU found in region '{region}'",
            }
        )

    machine_type = resource.attributes.get("machine_type")
    node_count = int(resource.attributes.get("node_count", 0))
    if machine_type and node_count > 0:
        disk_size = float(resource.attributes.get("disk_size_gb", 0))
        disk_type = resource.attributes.get("disk_type", "pd-standard")
        node_mappings, node_unpriced = map_gce_compute(
            region=region,
            machine_type=machine_type,
            node_count=node_count,
            disk_size_gb=disk_size,
            disk_type=disk_type,
            resource_quantity=resource.quantity,
            resource_id=resource.resource_id,
            cursor=cursor,
        )
        mappings.extend(node_mappings)
        unpriced.extend(node_unpriced)

    return mappings, unpriced


def map_gke_node_pool(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if region is None:
        return mappings, unpriced
    machine_type = resource.attributes.get("machine_type")
    node_count = int(resource.attributes.get("node_count", 3))
    disk_size = float(resource.attributes.get("disk_size_gb", 100))
    disk_type = resource.attributes.get("disk_type", "pd-standard")

    if not machine_type:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "Missing machine_type for GKE node pool",
            }
        )
        return mappings, unpriced

    node_mappings, node_unpriced = map_gce_compute(
        region=region,
        machine_type=machine_type,
        node_count=node_count,
        disk_size_gb=disk_size,
        disk_type=disk_type,
        resource_quantity=resource.quantity,
        resource_id=resource.resource_id,
        cursor=cursor,
    )
    mappings.extend(node_mappings)
    unpriced.extend(node_unpriced)

    return mappings, unpriced
