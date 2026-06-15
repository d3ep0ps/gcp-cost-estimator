# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_pubsub_topic(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    throughput = float(resource.usage.get("monthly_message_throughput_gb", 10.0))

    # Message throughput billing: $0.04/GB
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'PubsubThroughput'
        """
    )
    row = cursor.fetchone()
    if row:
        mappings.append(
            {
                "sku_id": row[0],
                "component": "message_throughput",
                "unit": row[1],
                "unit_price": row[2],
                "qty": throughput * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "No matching SKU found for Pub/Sub Message Throughput",
            }
        )

    return mappings, unpriced


def map_pubsub_subscription(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    retain_acked = resource.attributes.get("retain_acked_messages", False)
    if isinstance(retain_acked, str):
        retain_acked = retain_acked.lower() in {"true", "1", "yes"}
    else:
        retain_acked = bool(retain_acked)

    storage = float(resource.usage.get("subscription_storage_gb", 0.0))

    # Billed for retained messages storage if retain_acked_messages is True
    if retain_acked and storage > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'PubsubStorage'
            """
        )
        row = cursor.fetchone()
        if row:
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "retained_storage",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": storage * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "No matching SKU found for Pub/Sub Subscription Storage",
                }
            )

    return mappings, unpriced
