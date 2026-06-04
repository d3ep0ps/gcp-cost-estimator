import sqlite3
from datetime import UTC, datetime
from typing import Any

import pytest

from gcp_billing_mcp.core.pricing.cache import (
    get_cache_status,
    get_cached_price,
    init_db,
    update_cache,
)
from gcp_billing_mcp.core.pricing.gcp_fetch import refresh_pricing_cache


class MockResponse:
    def __init__(self, json_data: dict[str, Any], status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code != 200:
            raise Exception(f"HTTP error {self.status_code}")


class MockClient:
    def __init__(self, responses: list[MockResponse]) -> None:
        self.responses = responses
        self.calls = []
        self.sku_call_index = 0

    def get(self, url: str, **kwargs: Any) -> MockResponse:
        self.calls.append((url, kwargs))
        if url == "https://cloudbilling.googleapis.com/v1/services":
            return MockResponse(
                {
                    "services": [
                        {"displayName": "Compute Engine", "serviceId": "6F81-5844-456A"},
                        {"displayName": "Cloud SQL", "serviceId": "9662-B51E-5089"},
                    ]
                }
            )
        if self.sku_call_index < len(self.responses):
            resp = self.responses[self.sku_call_index]
            self.sku_call_index += 1
            return resp
        return MockResponse({"skus": []})


def test_refresh_respects_72h_cadence_unless_forced(temp_db_path: str) -> None:
    """Verify refresh is skipped if cache is younger than 72 hours and force is False."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Pre-populate cache metadata with recent timestamp
    conn = sqlite3.connect(temp_db_path)
    now_str = datetime.now(UTC).isoformat()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("gcp_last_refreshed_at", now_str),
        )
    conn.close()

    # Try to refresh, should be skipped
    client = MockClient([])
    result = refresh_pricing_cache(temp_db_path, force=False, client=client)
    assert result["status"] == "skipped"
    assert "not stale" in result["reason"].lower()
    assert len(client.calls) == 0

    # Try to force refresh, should call API (even if not stale)
    mock_sku_resp = {
        "skus": [
            {
                "skuId": "SKU-VCPU",
                "description": "N2 vCPU",
                "category": {
                    "serviceDisplayName": "Compute Engine",
                    "resourceFamily": "Compute",
                    "resourceGroup": "CPU",
                    "usageType": "OnDemand",
                },
                "serviceRegions": ["us-central1"],
                "pricingInfo": [
                    {
                        "pricingExpression": {
                            "usageUnit": "h",
                            "tieredRates": [
                                {
                                    "startUsageAmount": 0,
                                    "unitPrice": {"units": "0", "nanos": 47500000},
                                }
                            ],
                        }
                    }
                ],
            }
        ]
    }
    client = MockClient([MockResponse(mock_sku_resp)])
    result = refresh_pricing_cache(temp_db_path, force=True, client=client)
    assert result["status"] == "refreshed"
    assert result["sku_count"] == 1
    assert len(client.calls) > 0


def test_refresh_populates_cache_from_fixtured_api(temp_db_path: str) -> None:
    """Verify that fetching and parsing GCP SKU payloads populates the cache database."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    mock_sku_resp = {
        "skus": [
            {
                "skuId": "SKU-RAM",
                "description": "N2 RAM",
                "category": {
                    "serviceDisplayName": "Compute Engine",
                    "resourceFamily": "Compute",
                    "resourceGroup": "RAM",
                    "usageType": "OnDemand",
                },
                "serviceRegions": ["us-central1", "us-east1"],
                "pricingInfo": [
                    {
                        "pricingExpression": {
                            "usageUnit": "GiBy.mo",
                            "tieredRates": [
                                {
                                    "startUsageAmount": 0,
                                    "unitPrice": {"units": "0", "nanos": 11800000},
                                }
                            ],
                        }
                    }
                ],
            }
        ]
    }

    client = MockClient([MockResponse(mock_sku_resp)])
    # Force refresh
    result = refresh_pricing_cache(temp_db_path, force=True, client=client)
    assert result["status"] == "refreshed"
    # Should insert 2 rows (one for us-central1 and one for us-east1)
    assert result["sku_count"] == 2

    # Check cache status
    status = get_cache_status(temp_db_path, "gcp")
    assert status["sku_count"] == 2
    assert status["stale"] is False

    # Check cached price lookup
    price1 = get_cached_price(temp_db_path, "gcp", "SKU-RAM", "us-central1")
    assert price1 is not None
    assert price1["unit_price"] == 0.0118
    assert price1["unit"] == "GiBy.mo"

    price2 = get_cached_price(temp_db_path, "gcp", "SKU-RAM", "us-east1")
    assert price2 is not None
    assert price2["unit_price"] == 0.0118


def test_refresh_failure_keeps_previous_snapshot(temp_db_path: str) -> None:
    """Verify that a network failure aborts the transaction and keeps existing cache intact."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Pre-populate with valid cache data
    initial_skus = [
        {
            "sku_id": "SKU-OLD",
            "service": "compute",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.5,
            "sku_group": "vcpu",
        }
    ]
    update_cache(temp_db_path, "gcp", initial_skus, "2026-06-03T10:00:00Z")

    # Run refresh with client that raises an error (non-200 response)
    client = MockClient([MockResponse({}, status_code=500)])

    with pytest.raises(Exception, match="HTTP error 500"):
        refresh_pricing_cache(temp_db_path, force=True, client=client)

    # Cache should still contain old SKU
    status = get_cache_status(temp_db_path, "gcp")
    assert status["sku_count"] == 1
    assert status["last_refreshed_at"] == "2026-06-03T10:00:00Z"

    price = get_cached_price(temp_db_path, "gcp", "SKU-OLD", "us-central1")
    assert price is not None
    assert price["unit_price"] == 0.5
