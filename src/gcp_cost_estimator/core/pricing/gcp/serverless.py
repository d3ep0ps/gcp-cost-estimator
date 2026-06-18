# SPDX-License-Identifier: Apache-2.0

import logging
import math
import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.validation.utils import parse_k8s_quantity

logger = logging.getLogger("gcp_cost_estimator")


def map_cloud_run_service(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if not region:
        return mappings, unpriced

    cpu_str = parse_k8s_quantity(resource.attributes.get("cpu", "1"), is_cpu=True)
    memory_str = parse_k8s_quantity(resource.attributes.get("memory", "0.5"), is_cpu=False)
    try:
        cpu = float(cpu_str)
        memory = float(memory_str)
    except ValueError:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Invalid cpu '{cpu_str}' or memory '{memory_str}'",
            }
        )
        return mappings, unpriced

    cpu_idle = resource.attributes.get("cpu_idle", True)
    min_instances = int(resource.attributes.get("min_instance_count", 0))

    invocations = int(resource.usage.get("invocations_per_month", 10000))
    sec_per_inv = float(resource.usage.get("runtime_seconds_per_invocation", 1.0))
    active_seconds = float(invocations) * sec_per_inv

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description, sku_group
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND service = 'cloud run'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if not rows:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No pricing data for Cloud Run in region '{region}'",
            }
        )
        return mappings, unpriced

    cpu_active_sku = None
    cpu_idle_sku = None
    cpu_alloc_sku = None
    ram_active_sku = None
    ram_idle_sku = None
    ram_alloc_sku = None
    requests_sku = None
    gpu_sku = None

    for row in rows:
        _sku_id, _unit, _unit_price, desc, sku_group = row
        desc_lower = desc.lower()
        if sku_group == "CPU":
            if "active" in desc_lower:
                cpu_active_sku = row
            elif "idle" in desc_lower:
                cpu_idle_sku = row
            elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                cpu_alloc_sku = row
        elif sku_group == "RAM":
            if "active" in desc_lower:
                ram_active_sku = row
            elif "idle" in desc_lower:
                ram_idle_sku = row
            elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                ram_alloc_sku = row
        elif sku_group == "Requests":
            requests_sku = row
        elif sku_group == "GPU":
            gpu_sku = row

    if not cpu_idle:
        target_cpu_sku = cpu_alloc_sku or cpu_active_sku
        if target_cpu_sku:
            mappings.append(
                {
                    "sku_id": target_cpu_sku[0],
                    "component": "vcpu",
                    "unit": target_cpu_sku[1],
                    "unit_price": target_cpu_sku[2],
                    "qty": cpu * 730 * 3600 * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No CPU allocation SKU found for Cloud Run in region '{region}'",
                }
            )

        target_ram_sku = ram_alloc_sku or ram_active_sku
        if target_ram_sku:
            mappings.append(
                {
                    "sku_id": target_ram_sku[0],
                    "component": "ram",
                    "unit": target_ram_sku[1],
                    "unit_price": target_ram_sku[2],
                    "qty": memory * 730 * 3600 * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No RAM allocation SKU found for Cloud Run in region '{region}'",
                }
            )
    else:
        if cpu_active_sku:
            mappings.append(
                {
                    "sku_id": cpu_active_sku[0],
                    "component": "vcpu",
                    "unit": cpu_active_sku[1],
                    "unit_price": cpu_active_sku[2],
                    "qty": active_seconds * cpu * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No CPU active SKU found for Cloud Run in region '{region}'",
                }
            )

        if ram_active_sku:
            mappings.append(
                {
                    "sku_id": ram_active_sku[0],
                    "component": "ram",
                    "unit": ram_active_sku[1],
                    "unit_price": ram_active_sku[2],
                    "qty": active_seconds * memory * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No RAM active SKU found for Cloud Run in region '{region}'",
                }
            )

        if min_instances > 0:
            total_cpu_warm = float(min_instances) * cpu * 730 * 3600
            total_ram_warm = float(min_instances) * memory * 730 * 3600

            cpu_idle_qty = max(0.0, total_cpu_warm - (active_seconds * cpu))
            ram_idle_qty = max(0.0, total_ram_warm - (active_seconds * memory))

            if cpu_idle_sku:
                mappings.append(
                    {
                        "sku_id": cpu_idle_sku[0],
                        "component": "vcpu_idle",
                        "unit": cpu_idle_sku[1],
                        "unit_price": cpu_idle_sku[2],
                        "qty": cpu_idle_qty * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No CPU idle SKU found for Cloud Run in region '{region}'",
                    }
                )

            if ram_idle_sku:
                mappings.append(
                    {
                        "sku_id": ram_idle_sku[0],
                        "component": "ram_idle",
                        "unit": ram_idle_sku[1],
                        "unit_price": ram_idle_sku[2],
                        "qty": ram_idle_qty * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No RAM idle SKU found for Cloud Run in region '{region}'",
                    }
                )

    if requests_sku:
        mappings.append(
            {
                "sku_id": requests_sku[0],
                "component": "requests",
                "unit": requests_sku[1],
                "unit_price": requests_sku[2],
                "qty": float(invocations) * resource.quantity,
            }
        )

    gpu_type = resource.attributes.get("gpu_type")
    gpu_count_str = resource.attributes.get("gpu_count", "0")
    try:
        gpu_count = int(gpu_count_str)
    except ValueError:
        gpu_count = 0

    if gpu_type and gpu_count > 0:
        if gpu_sku:
            gpu_seconds = (730 * 3600) if not cpu_idle else active_seconds
            mappings.append(
                {
                    "sku_id": gpu_sku[0],
                    "component": "gpu",
                    "unit": gpu_sku[1],
                    "unit_price": gpu_sku[2],
                    "qty": float(gpu_count) * gpu_seconds * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No GPU SKU found for Cloud Run in region '{region}'",
                }
            )

    return mappings, unpriced


def map_cloud_run_job(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if not region:
        return mappings, unpriced

    cpu_str = parse_k8s_quantity(resource.attributes.get("cpu", "1"), is_cpu=True)
    memory_str = parse_k8s_quantity(resource.attributes.get("memory", "0.5"), is_cpu=False)
    try:
        cpu = float(cpu_str)
        memory = float(memory_str)
    except ValueError:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Invalid cpu '{cpu_str}' or memory '{memory_str}'",
            }
        )
        return mappings, unpriced

    task_count = int(resource.usage.get("task_count", 1))
    seconds_per_task = float(resource.usage.get("runtime_seconds_per_task", 60.0))
    executions = int(resource.usage.get("executions_per_month", 100))

    billed_seconds_per_task = max(60.0, seconds_per_task)
    total_seconds = billed_seconds_per_task * float(task_count) * float(executions)

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description, sku_group
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND service = 'cloud run'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if not rows:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No pricing data for Cloud Run in region '{region}'",
            }
        )
        return mappings, unpriced

    cpu_alloc_sku = None
    cpu_active_sku = None
    ram_alloc_sku = None
    ram_active_sku = None
    gpu_sku = None

    for row in rows:
        _sku_id, _unit, _unit_price, desc, sku_group = row
        desc_lower = desc.lower()
        if sku_group == "CPU":
            if "active" in desc_lower:
                cpu_active_sku = row
            elif "idle" in desc_lower:
                logger.debug("Idle CPU SKU ignored for Cloud Run Job: %s", _sku_id)
                continue
            elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                cpu_alloc_sku = row
        elif sku_group == "RAM":
            if "active" in desc_lower:
                ram_active_sku = row
            elif "idle" in desc_lower:
                logger.debug("Idle RAM SKU ignored for Cloud Run Job: %s", _sku_id)
                continue
            elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                ram_alloc_sku = row
        elif sku_group == "GPU":
            gpu_sku = row

    target_cpu_sku = cpu_alloc_sku or cpu_active_sku
    if target_cpu_sku:
        mappings.append(
            {
                "sku_id": target_cpu_sku[0],
                "component": "vcpu",
                "unit": target_cpu_sku[1],
                "unit_price": target_cpu_sku[2],
                "qty": total_seconds * cpu * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No CPU allocation SKU found for Cloud Run in region '{region}'",
            }
        )

    target_ram_sku = ram_alloc_sku or ram_active_sku
    if target_ram_sku:
        mappings.append(
            {
                "sku_id": target_ram_sku[0],
                "component": "ram",
                "unit": target_ram_sku[1],
                "unit_price": target_ram_sku[2],
                "qty": total_seconds * memory * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No RAM allocation SKU found for Cloud Run in region '{region}'",
            }
        )

    gpu_type = resource.attributes.get("gpu_type")
    gpu_count_str = resource.attributes.get("gpu_count", "0")
    try:
        gpu_count = int(gpu_count_str)
    except ValueError:
        gpu_count = 0

    if gpu_type and gpu_count > 0:
        if gpu_sku:
            mappings.append(
                {
                    "sku_id": gpu_sku[0],
                    "component": "gpu",
                    "unit": gpu_sku[1],
                    "unit_price": gpu_sku[2],
                    "qty": float(gpu_count) * total_seconds * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No GPU SKU found for Cloud Run in region '{region}'",
                }
            )

    return mappings, unpriced


def map_cloud_function(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    gen = resource.attributes.get("generation", "1st_gen")
    if gen == "2nd_gen":
        return map_cloud_run_service(resource, cursor)

    region = resource.region
    if not region:
        return mappings, unpriced

    memory_mb = resource.attributes.get("available_memory_mb", 256)
    try:
        memory_gb = float(resource.attributes.get("memory_gb", float(memory_mb) / 1024.0))
        cpu_ghz = float(resource.attributes.get("cpu_ghz", 0.4))
    except ValueError, TypeError:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "Invalid memory/cpu attributes for function",
            }
        )
        return mappings, unpriced

    invocations = int(resource.usage.get("invocations_per_month", 1_000_000))
    avg_execution_time_ms = float(resource.usage.get("avg_execution_time_ms", 100.0))

    rounded_duration_sec = math.ceil(avg_execution_time_ms / 100.0) * 0.1
    active_seconds = float(invocations) * rounded_duration_sec

    min_instances = int(resource.attributes.get("min_instances", 0))

    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description, sku_group
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND service = 'cloud functions'
        """,
        (region,),
    )
    rows = cursor.fetchall()
    if not rows:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No pricing data for Cloud Functions in region '{region}'",
            }
        )
        return mappings, unpriced

    invocations_sku = None
    cpu_active_sku = None
    cpu_idle_sku = None
    ram_active_sku = None
    ram_idle_sku = None

    for row in rows:
        _sku_id, _unit, _unit_price, desc, sku_group = row
        desc_lower = desc.lower()
        if sku_group == "Invocations" or "invocation" in desc_lower:
            invocations_sku = row
        elif sku_group == "GHz-second" or "ghz" in desc_lower:
            if "idle" in desc_lower:
                cpu_idle_sku = row
            else:
                cpu_active_sku = row
        elif sku_group == "GB-second" or "gb" in desc_lower:
            if "idle" in desc_lower:
                ram_idle_sku = row
            else:
                ram_active_sku = row

    if invocations_sku:
        mappings.append(
            {
                "sku_id": invocations_sku[0],
                "component": "requests",
                "unit": invocations_sku[1],
                "unit_price": invocations_sku[2],
                "qty": float(invocations) * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No Invocations SKU found for Cloud Functions in region '{region}'",
            }
        )

    if cpu_active_sku:
        mappings.append(
            {
                "sku_id": cpu_active_sku[0],
                "component": "vcpu",
                "unit": cpu_active_sku[1],
                "unit_price": cpu_active_sku[2],
                "qty": active_seconds * cpu_ghz * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (
                    f"No active GHz-second CPU SKU found for Cloud Functions in region '{region}'"
                ),
            }
        )

    if ram_active_sku:
        mappings.append(
            {
                "sku_id": ram_active_sku[0],
                "component": "ram",
                "unit": ram_active_sku[1],
                "unit_price": ram_active_sku[2],
                "qty": active_seconds * memory_gb * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (
                    f"No active GB-second Memory SKU found for Cloud Functions in region '{region}'"
                ),
            }
        )

    if min_instances > 0:
        total_idle_seconds = max(0.0, float(min_instances) * 730.0 * 3600.0 - active_seconds)

        target_cpu_idle_sku = cpu_idle_sku or cpu_active_sku
        if target_cpu_idle_sku:
            mappings.append(
                {
                    "sku_id": target_cpu_idle_sku[0],
                    "component": "vcpu_idle",
                    "unit": target_cpu_idle_sku[1],
                    "unit_price": target_cpu_idle_sku[2],
                    "qty": total_idle_seconds * cpu_ghz * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        f"No GHz-second CPU idle SKU found for Cloud Functions in region '{region}'"
                    ),
                }
            )

        target_ram_idle_sku = ram_idle_sku or ram_active_sku
        if target_ram_idle_sku:
            mappings.append(
                {
                    "sku_id": target_ram_idle_sku[0],
                    "component": "ram_idle",
                    "unit": target_ram_idle_sku[1],
                    "unit_price": target_ram_idle_sku[2],
                    "qty": total_idle_seconds * memory_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        f"No GB-second Memory idle SKU found for "
                        f"Cloud Functions in region '{region}'"
                    ),
                }
            )

    return mappings, unpriced
