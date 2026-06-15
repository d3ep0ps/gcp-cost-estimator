# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.gcp.compute import map_gce_compute


def map_dataproc_cluster(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region or "us-central1"
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 100.0))

    # Dataproc Cluster Premium SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'DataprocPremium' AND region = ?
        """,
        (region,),
    )
    premium_row = cursor.fetchone()
    if not premium_row:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (
                    f"Region '{region}' not supported or "
                    "missing premium pricing data for Dataproc"
                ),
            }
        )
        return mappings, unpriced

    # Extract node counts and specs
    num_master_nodes = int(resource.attributes.get("num_master_nodes", 1))
    num_worker_nodes = int(resource.attributes.get("num_worker_nodes", 2))
    num_preemptible_nodes = int(resource.attributes.get("num_preemptible_nodes", 0))

    master_vcpus = int(resource.usage.get("num_master_vcpus", 4))
    worker_vcpus = int(resource.usage.get("num_worker_vcpus", 4))

    # 1. Premium cost calculation (master + workers + preemptible workers)
    total_vcpus = (num_master_nodes * master_vcpus) + (
        (num_worker_nodes + num_preemptible_nodes) * worker_vcpus
    )
    total_premium_hours = total_vcpus * runtime_hours * resource.quantity

    mappings.append(
        {
            "sku_id": premium_row[0],
            "component": "dataproc_premium",
            "unit": premium_row[1],
            "unit_price": premium_row[2],
            "qty": total_premium_hours,
        }
    )

    # 2. Delegate underlying Compute Engine VM costs to compute.py (disk_size = 0)
    master_machine_type = resource.attributes.get("master_machine_type", "n1-standard-4")
    worker_machine_type = resource.attributes.get("worker_machine_type", "n1-standard-4")

    # Master VMs
    if num_master_nodes > 0:
        master_mappings, master_unpriced = map_gce_compute(
            region=region,
            machine_type=master_machine_type,
            node_count=num_master_nodes,
            disk_size_gb=0,
            disk_type="",
            resource_quantity=resource.quantity,
            resource_id=resource.resource_id,
            cursor=cursor,
        )
        mappings.extend(master_mappings)
        unpriced.extend(master_unpriced)

    # Normal worker VMs
    if num_worker_nodes > 0:
        worker_mappings, worker_unpriced = map_gce_compute(
            region=region,
            machine_type=worker_machine_type,
            node_count=num_worker_nodes,
            disk_size_gb=0,
            disk_type="",
            resource_quantity=resource.quantity,
            resource_id=resource.resource_id,
            cursor=cursor,
        )
        mappings.extend(worker_mappings)
        unpriced.extend(worker_unpriced)

    # Preemptible worker VMs
    if num_preemptible_nodes > 0:
        preempt_mappings, preempt_unpriced = map_gce_compute(
            region=region,
            machine_type=worker_machine_type,
            node_count=num_preemptible_nodes,
            disk_size_gb=0,
            disk_type="",
            resource_quantity=resource.quantity,
            resource_id=resource.resource_id,
            cursor=cursor,
        )
        # SkuMapper / calc will price preemptible workers at standard CPU/RAM in v1 (ADR-003)
        mappings.extend(preempt_mappings)
        unpriced.extend(preempt_unpriced)

    return mappings, unpriced
