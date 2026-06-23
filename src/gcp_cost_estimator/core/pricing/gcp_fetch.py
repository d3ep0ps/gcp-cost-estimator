# SPDX-License-Identifier: Apache-2.0

import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from gcp_cost_estimator.core.pricing.cache import (
    get_cache_status,
    resolve_service_ids_from_catalog,
    update_cache,
    update_services_catalog,
)
from gcp_cost_estimator.core.registries import get_sku_mapper_class

logger = logging.getLogger("gcp_cost_estimator")

# Last-resort fallback if Google services catalog cannot be fetched/resolved.
FALLBACK_GCP_SERVICES = {
    "Compute Engine": "6F81-5844-456A",
    "Cloud SQL": "9662-B51E-5089",
    "Cloud Storage": "95FF-2A5F-EC25",
    "Cloud Run": "152E-C115-5142",
    "Cloud Functions": "29E7-DA93-CA13",
    "App Engine": "7AF5-250D-495A",
}


def refresh_pricing_cache(
    db_path: str, force: bool = False, client: Any | None = None
) -> dict[str, Any]:
    """Refresh the pricing cache by fetching SKUs for all supported provider services.

    First queries the Billing services catalog to cache all service IDs, resolves
    the required services from the registered SkuMapper class, and then fetches
    SKUs for each resolved service ID.
    """
    status = get_cache_status(db_path, "gcp")
    if not force and not status["stale"]:
        return {
            "status": "skipped",
            "reason": f"Cache is not stale (age: {status['age_hours']:.1f} hours, threshold: 72).",
        }

    # Fetch and parse SKUs
    parsed_skus: list[dict[str, Any]] = []
    local_client = client if client is not None else httpx.Client()

    try:
        # Read credentials
        api_key = os.environ.get("GCP_API_KEY")
        access_token = os.environ.get("GCP_ACCESS_TOKEN")

        params: dict[str, Any] = {}
        headers: dict[str, str] = {}

        if api_key:
            headers["X-Goog-Api-Key"] = api_key
        elif access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        else:
            # Attempt to fall back to gcloud if available
            import subprocess

            try:
                proc = subprocess.run(
                    ["gcloud", "auth", "print-access-token"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
                if proc.returncode == 0:
                    token = proc.stdout.strip()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
            except Exception:
                pass

        # 1. Fetch complete list of GCP services from Billing API and update services catalog in DB
        services_url = "https://cloudbilling.googleapis.com/v1/services"
        try:
            logger.info("Fetching complete services catalog from: %s", services_url)
            response = local_client.get(services_url, params=params, headers=headers)
            response.raise_for_status()
            services_data = response.json().get("services", [])
            if services_data:
                update_services_catalog(db_path, "gcp", services_data)
                logger.info(
                    "Successfully updated service catalog with %d services", len(services_data)
                )
        except Exception as e:
            logger.warning(
                "Failed to refresh dynamic services catalog from GCP: %s. Using cached copy.", e
            )

        # 2. Get list of display names our mapper currently requires
        mapper_class = get_sku_mapper_class("gcp")
        if not mapper_class:
            raise ValueError("No SkuMapper registered for provider 'gcp'")

        target_display_names = mapper_class.get_supported_billing_services()
        logger.info("Provider SkuMapper requires billing services: %s", target_display_names)

        # 3. Resolve service IDs using the SQLite catalog
        resolved_service_ids = resolve_service_ids_from_catalog(
            db_path, "gcp", target_display_names
        )

        # For any missing, attempt to use static fallbacks or log warning
        final_services: dict[str, str] = {}
        for display_name in target_display_names:
            if display_name in resolved_service_ids:
                final_services[display_name] = resolved_service_ids[display_name]
            elif display_name in FALLBACK_GCP_SERVICES:
                logger.warning(
                    "Service '%s' not found in database catalog. Using fallback.", display_name
                )
                final_services[display_name] = FALLBACK_GCP_SERVICES[display_name]
            else:
                logger.error(
                    "Required service '%s' could not be resolved. SKUs will not be fetched.",
                    display_name,
                )

        # 4. Fetch SKUs for each resolved service ID
        for service_name, service_id in final_services.items():
            url = f"https://cloudbilling.googleapis.com/v1/services/{service_id}/skus"
            logger.info("Fetching pricing SKUs from Google Billing API URL: %s", url)
            next_page_token = ""

            # Fetch pages
            while True:
                local_params = params.copy()
                if next_page_token:
                    local_params["pageToken"] = next_page_token

                response = local_client.get(url, params=local_params, headers=headers)
                response.raise_for_status()
                payload = response.json()

                skus = payload.get("skus", [])
                for sku in skus:
                    sku_id = sku.get("skuId")
                    description = sku.get("description", "")
                    category = sku.get("category", {})
                    service = category.get("serviceDisplayName", service_name)
                    sku_group = category.get("resourceGroup", "Other")
                    regions = sku.get("serviceRegions", [])
                    pricing_info = sku.get("pricingInfo", [])

                    if not sku_id or not pricing_info:
                        continue

                    pricing_expr = pricing_info[0].get("pricingExpression", {})
                    unit = pricing_expr.get("usageUnit", "hour")
                    rates = pricing_expr.get("tieredRates", [])

                    if not rates:
                        continue

                    unit_price_data = rates[0].get("unitPrice", {})
                    try:
                        units = int(unit_price_data.get("units", 0))
                        nanos = int(unit_price_data.get("nanos", 0))
                    except (ValueError, TypeError):
                        units = 0
                        nanos = 0

                    unit_price = units + nanos / 1_000_000_000.0

                    for r in regions:
                        parsed_skus.append(
                            {
                                "sku_id": sku_id,
                                "service": service.lower(),
                                "region": r,
                                "unit": unit,
                                "unit_price": unit_price,
                                "sku_group": sku_group,
                                "description": description,
                            }
                        )

                next_page_token = payload.get("nextPageToken", "")
                if not next_page_token or client is not None:
                    break

        now_iso = datetime.now(UTC).isoformat()
        update_cache(db_path, "gcp", parsed_skus, now_iso)

        return {
            "status": "refreshed",
            "sku_count": len(parsed_skus),
            "snapshot_ts": now_iso,
        }
    finally:
        if client is None:
            local_client.close()
