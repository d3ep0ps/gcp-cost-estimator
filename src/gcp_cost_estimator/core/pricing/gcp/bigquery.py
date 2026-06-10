# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_bigquery_dataset(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    if not region:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "Missing region for BigQuery dataset",
            }
        )
        return mappings, unpriced

    pricing_model = resource.attributes.get("pricing_model", "on-demand")
    if pricing_model == "capacity":
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": ("Capacity pricing requires slot commitments; not statically estimable"),
            }
        )
        return mappings, unpriced

    active_storage_gb = float(resource.usage.get("active_storage_gb", 0))
    long_term_storage_gb = float(resource.usage.get("long_term_storage_gb", 0))
    monthly_query_tb = float(resource.usage.get("monthly_query_tb", 0))
    monthly_streaming_gb = float(resource.usage.get("monthly_streaming_gb", 0))

    # 1. Active storage
    if active_storage_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
            AND (description LIKE '%Active%')
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "active_storage",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": active_storage_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching active storage SKU found for region '{region}'",
                }
            )

    # 2. Long-term storage
    if long_term_storage_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
            AND (description LIKE '%Long Term%')
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "long_term_storage",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": long_term_storage_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching long-term storage SKU found for region '{region}'",
                }
            )

    # 3. Query scan (Analysis)
    if monthly_query_tb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryAnalysis'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "query_scan",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": monthly_query_tb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching query scan SKU found for region '{region}'",
                }
            )

    # 4. Streaming insert
    if monthly_streaming_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStreaming'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if rows:
            match = rows[0]
            mappings.append(
                {
                    "sku_id": match[0],
                    "component": "streaming_insert",
                    "unit": match[1],
                    "unit_price": match[2],
                    "qty": monthly_streaming_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching streaming insert SKU found for region '{region}'",
                }
            )

    return mappings, unpriced
