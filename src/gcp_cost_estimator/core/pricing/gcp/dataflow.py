# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_dataflow_job(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region or "us-central1"
    job_type = resource.usage.get("job_type", "batch")
    runtime_hours = float(resource.usage.get("runtime_hours_per_month", 100.0))
    max_workers = int(resource.attributes.get("max_workers", 1))

    # We only support regions that exist in our pricing fixtures
    # Let's verify the region has a valid CPU SKU first
    sku_group_cpu = "DataflowBatchVcpu" if job_type == "batch" else "DataflowStreamingVcpu"
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = ? AND region = ?
        """,
        (sku_group_cpu, region),
    )
    cpu_row = cursor.fetchone()
    if not cpu_row:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (f"Region '{region}' not supported or missing pricing data for Dataflow"),
            }
        )
        return mappings, unpriced

    # 1. vCPU cost
    num_vcpus = float(resource.usage.get("num_vcpus", 4.0))
    mappings.append(
        {
            "sku_id": cpu_row[0],
            "component": "vcpu",
            "unit": cpu_row[1],
            "unit_price": cpu_row[2],
            "qty": num_vcpus * max_workers,
        }
    )

    # 2. Memory cost
    sku_group_ram = "DataflowBatchMemory" if job_type == "batch" else "DataflowStreamingMemory"
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = ? AND region = ?
        """,
        (sku_group_ram, region),
    )
    ram_row = cursor.fetchone()
    if ram_row:
        memory_gb = float(resource.usage.get("memory_gb", 15.0))
        mappings.append(
            {
                "sku_id": ram_row[0],
                "component": "ram",
                "unit": ram_row[1],
                "unit_price": ram_row[2],
                "qty": memory_gb * max_workers,
            }
        )

    # 3. Storage cost (PD standard hourly billing)
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'DataflowStorage' AND region = ?
        """,
        (region,),
    )
    storage_row = cursor.fetchone()
    if storage_row:
        disk_size = float(resource.attributes.get("disk_size_gb") or 250.0)
        total_storage_hours = disk_size * max_workers * runtime_hours
        mappings.append(
            {
                "sku_id": storage_row[0],
                "component": "storage",
                "unit": storage_row[1],
                "unit_price": storage_row[2],
                "qty": total_storage_hours,
            }
        )

    # 4. Job type specific costs
    if job_type == "batch":
        # Shuffle billing with volume adjustments
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'DataflowShuffle' AND region = ?
            """,
            (region,),
        )
        shuffle_row = cursor.fetchone()
        if shuffle_row:
            raw_shuffle = float(resource.usage.get("shuffle_data_gb", 50.0))
            # First 250 GiB -> 75% reduction (pay 25%)
            # next 4870 GiB -> 50% reduction (pay 50%)
            # above -> no reduction
            if raw_shuffle <= 250.0:
                billable_shuffle = raw_shuffle * 0.25
            elif raw_shuffle <= 5120.0:
                billable_shuffle = 250.0 * 0.25 + (raw_shuffle - 250.0) * 0.5
            else:
                billable_shuffle = 250.0 * 0.25 + 4870.0 * 0.5 + (raw_shuffle - 5120.0)

            mappings.append(
                {
                    "sku_id": shuffle_row[0],
                    "component": "shuffle",
                    "unit": shuffle_row[1],
                    "unit_price": shuffle_row[2],
                    "qty": billable_shuffle,
                }
            )
    else:
        # Streaming Engine billing
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'DataflowStreamingEngine' AND region = ?
            """,
            (region,),
        )
        engine_row = cursor.fetchone()
        if engine_row:
            default_units = max(1.0, num_vcpus / 4.0)
            num_units = float(resource.usage.get("num_streaming_engine_units", default_units))
            total_engine_hours = num_units * runtime_hours
            mappings.append(
                {
                    "sku_id": engine_row[0],
                    "component": "streaming_engine",
                    "unit": engine_row[1],
                    "unit_price": engine_row[2],
                    "qty": total_engine_hours,
                }
            )

    return mappings, unpriced
