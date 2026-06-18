# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource


def map_cloud_cdn_backend(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    cdn_enabled = resource.attributes.get("cdn_enabled", False)
    if not cdn_enabled:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "No cdn_policy block — CDN not enabled",
            }
        )
        return mappings, unpriced

    region = resource.region
    if not region:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": "No region specified for Cloud CDN backend",
            }
        )
        return mappings, unpriced

    # 1. Cache Transfer Out
    tx_gb = float(resource.usage.get("monthly_cache_transfer_gb", 0))
    if tx_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'CdnCacheTransferOut'
            """,
            (region,),
        )
        row = cursor.fetchone()
        if row:
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "cache_transfer_out",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": tx_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        f"No matching Cloud CDN Cache Transfer Out SKU found for region '{region}'"
                    ),
                }
            )

    # 2. Cache Fill
    fill_gb = float(resource.usage.get("monthly_cache_fill_gb", 0))
    if fill_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'CdnCacheFill'
            """,
            (region,),
        )
        row = cursor.fetchone()
        if row:
            mappings.append(
                {
                    "sku_id": row[0],
                    "component": "cache_fill",
                    "unit": row[1],
                    "unit_price": row[2],
                    "qty": fill_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (f"No matching Cloud CDN Cache Fill SKU found for region '{region}'"),
                }
            )

    # 3. Requests
    requests = float(resource.usage.get("monthly_requests", 0))
    if requests > 0:
        https_frac = float(resource.usage.get("https_fraction", 1.0))
        https_reqs = requests * https_frac
        http_reqs = requests * (1.0 - https_frac)

        if http_reqs > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'CdnRequests'
                AND (description LIKE '%HTTP %' OR description LIKE '%HTTP Requests%'
                     OR description = 'Cloud CDN HTTP Requests')
                """,
                (region,),
            )
            row = cursor.fetchone()
            if row:
                mappings.append(
                    {
                        "sku_id": row[0],
                        "component": "http_requests",
                        "unit": row[1],
                        "unit_price": row[2],
                        "qty": (http_reqs / 10000.0) * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": (
                            f"No matching Cloud CDN HTTP Requests SKU found for region '{region}'"
                        ),
                    }
                )

        if https_reqs > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'CdnRequests'
                AND (description LIKE '%HTTPS%' or description = 'Cloud CDN HTTPS Requests')
                """,
                (region,),
            )
            row = cursor.fetchone()
            if row:
                mappings.append(
                    {
                        "sku_id": row[0],
                        "component": "https_requests",
                        "unit": row[1],
                        "unit_price": row[2],
                        "qty": (https_reqs / 10000.0) * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": (
                            f"No matching Cloud CDN HTTPS Requests SKU found for region '{region}'"
                        ),
                    }
                )

    return mappings, unpriced
