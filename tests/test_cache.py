# SPDX-License-Identifier: Apache-2.0

import sqlite3
from datetime import UTC

import pytest

from gcp_billing_mcp.core.pricing.cache import (
    get_cache_status,
    get_cached_price,
    init_db,
    update_cache,
)


def test_cache_roundtrip_sku_and_price(temp_db_path: str) -> None:
    """Verify that writing SKUs to the cache and reading them back works."""
    # Initialize DB
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    skus = [
        {
            "sku_id": "GCP-SKU-1",
            "service": "compute",
            "region": "us-central1",
            "unit": "hour",
            "unit_price": 0.0475,
            "sku_group": "n2-standard-4-vcpu",
        },
        {
            "sku_id": "GCP-SKU-2",
            "service": "compute",
            "region": "us-central1",
            "unit": "gibibyte-month",
            "unit_price": 0.0118,
            "sku_group": "n2-standard-4-ram",
        },
    ]

    # Write to cache
    update_cache(temp_db_path, "gcp", skus, "2026-06-03T12:00:00Z")

    # Read back prices
    price1 = get_cached_price(temp_db_path, "gcp", "GCP-SKU-1", "us-central1")
    assert price1 is not None
    assert price1["unit_price"] == 0.0475
    assert price1["unit"] == "hour"
    assert price1["service"] == "compute"

    price2 = get_cached_price(temp_db_path, "gcp", "GCP-SKU-2", "us-central1")
    assert price2 is not None
    assert price2["unit_price"] == 0.0118
    assert price2["sku_group"] == "n2-standard-4-ram"


def test_get_cache_status_reports_age_and_count(temp_db_path: str) -> None:
    """Verify that cache status calculates correctly."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Empty cache status
    status = get_cache_status(temp_db_path, "gcp")
    assert status["sku_count"] == 0
    assert status["stale"] is True  # No timestamp = stale

    skus = [
        {
            "sku_id": "GCP-SKU-1",
            "service": "compute",
            "region": "us-central1",
            "unit": "hour",
            "unit_price": 0.0475,
            "sku_group": "vcpu",
        }
    ]

    # Set mock current time context via snapshot datetime string
    # We can write a test using a recently updated timestamp
    from datetime import datetime, timedelta

    now_utc = datetime.now(UTC)

    # 10 hours ago
    ten_hours_ago = (now_utc - timedelta(hours=10)).isoformat()
    update_cache(temp_db_path, "gcp", skus, ten_hours_ago)

    status = get_cache_status(temp_db_path, "gcp")
    assert status["sku_count"] == 1
    assert 9 <= status["age_hours"] <= 11
    assert status["stale"] is False

    # 80 hours ago (stale)
    eighty_hours_ago = (now_utc - timedelta(hours=80)).isoformat()
    update_cache(temp_db_path, "gcp", skus, eighty_hours_ago)

    status = get_cache_status(temp_db_path, "gcp")
    assert status["sku_count"] == 1
    assert status["stale"] is True


def test_atomic_swap_does_not_corrupt_on_failed_refresh(temp_db_path: str) -> None:
    """Verify that a failure during update does not corrupt existing cache data."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    skus = [
        {
            "sku_id": "GCP-SKU-EXISTING",
            "service": "compute",
            "region": "us-central1",
            "unit": "hour",
            "unit_price": 1.0,
            "sku_group": "vcpu",
        }
    ]
    update_cache(temp_db_path, "gcp", skus, "2026-06-03T12:00:00Z")

    # Attempt to write invalid skus list (contains dict without required key,
    # which will raise TypeError or KeyError)
    invalid_skus = [
        {
            "sku_id": "GCP-SKU-NEW",
            "service": "compute",
            # missing region, unit, unit_price
        }
    ]

    with pytest.raises((KeyError, sqlite3.Error, TypeError)):
        update_cache(temp_db_path, "gcp", invalid_skus, "2026-06-03T13:00:00Z")

    # Confirm original cache is still intact
    price = get_cached_price(temp_db_path, "gcp", "GCP-SKU-EXISTING", "us-central1")
    assert price is not None
    assert price["unit_price"] == 1.0


def test_lookup_unknown_sku_returns_none_not_error(temp_db_path: str) -> None:
    """Verify that looking up non-existent SKUs returns None."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    price = get_cached_price(temp_db_path, "gcp", "NONEXISTENT", "us-central1")
    assert price is None
