# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_compute_security_policy(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    requests = float(resource.usage.get("monthly_requests", 1000000))
    rule_count = int(resource.attributes.get("rule_count", 0))

    # 1. Policy cost: $5.00/policy/month
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND sku_group = 'ArmorPolicy'
        """
    )
    row = cursor.fetchone()
    if row:
        mappings.append(
            {
                "sku_id": row[0],
                "component": "security_policy",
                "unit": row[1],
                "unit_price": row[2],
                "qty": 1.0 * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "No matching SKU found for Cloud Armor Security Policy",
            }
        )

    # 2. Rule cost: $1.00/rule/month
    if rule_count > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'ArmorRule'
            """
        )
        row = cursor.fetchone()
        if row:
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "security_rules",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": float(rule_count) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "No matching SKU found for Cloud Armor Security Rule",
                }
            )

    # 3. Request cost: $0.75/million requests
    if requests > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND sku_group = 'ArmorRequests'
            """
        )
        row = cursor.fetchone()
        if row:
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "requests",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": (requests / 1000000.0) * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "No matching SKU found for Cloud Armor Requests",
                }
            )

    return mappings, unpriced
