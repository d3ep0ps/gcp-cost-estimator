# SPDX-License-Identifier: Apache-2.0

import os

import httpx
import pytest

from gcp_cost_estimator.core.pricing.cache import get_cache_status
from gcp_cost_estimator.core.pricing.gcp_fetch import refresh_pricing_cache


@pytest.fixture(autouse=True)
def require_gcp_credentials() -> None:
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or not os.environ.get("GCP_BILLING_PROJECT"):
        pytest.skip("GCP integration credentials not set.")


@pytest.mark.integration
def test_integration_gcp_api_refresh(temp_db_path: str) -> None:
    """Opt-in integration test that makes a real call to the Google Cloud Billing API.

    Verifies that we can fetch and cache SKUs properly without mock clients.
    """
    # Refresh the pricing cache (this makes a real network request)
    try:
        result = refresh_pricing_cache(temp_db_path, force=True)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            pytest.skip(
                "GCP Cloud Billing API returned 403 Forbidden. "
                "Ensure GCP_API_KEY or GCP_ACCESS_TOKEN is set, or authenticate using gcloud."
            )
        raise

    # Verify response structure
    assert result["status"] == "refreshed"
    assert result["sku_count"] > 0
    assert "snapshot_ts" in result

    # Check cache status
    status = get_cache_status(temp_db_path, "gcp")
    assert status["stale"] is False
    assert status["age_hours"] < 1.0
