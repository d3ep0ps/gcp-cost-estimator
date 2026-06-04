# SPDX-License-Identifier: Apache-2.0

import sqlite3
from datetime import UTC, datetime
from typing import Any


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize SQLite database tables for cache storage."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pricing_cache (
                provider TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                service TEXT NOT NULL,
                region TEXT NOT NULL,
                unit TEXT NOT NULL,
                unit_price REAL NOT NULL,
                sku_group TEXT NOT NULL,
                description TEXT NOT NULL,
                snapshot_ts TEXT NOT NULL,
                PRIMARY KEY (provider, sku_id, region)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS billing_services (
                provider TEXT NOT NULL,
                service_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                name TEXT NOT NULL,
                PRIMARY KEY (provider, service_id)
            )
        """)


def update_services_catalog(db_path: str, provider: str, services: list[dict[str, Any]]) -> None:
    """Save the complete catalog of services to the SQLite database."""
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        with conn:
            for s in services:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO billing_services (
                        provider, service_id, display_name, name
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        provider,
                        s.get("serviceId", ""),
                        s.get("displayName", ""),
                        s.get("name", ""),
                    ),
                )
    finally:
        conn.close()


def resolve_service_ids_from_catalog(
    db_path: str, provider: str, display_names: list[str]
) -> dict[str, str]:
    """Query the SQLite database to resolve service IDs for a list of display names."""
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        cursor = conn.cursor()
        resolved: dict[str, str] = {}
        for dn in display_names:
            cursor.execute(
                """
                SELECT service_id
                FROM billing_services
                WHERE provider = ? AND LOWER(display_name) = ?
                """,
                (provider, dn.lower()),
            )
            row = cursor.fetchone()
            if row:
                resolved[dn] = row[0]
        return resolved
    finally:
        conn.close()


def get_cache_status(db_path: str, provider: str) -> dict[str, Any]:
    """Retrieve cache metadata status, calculating age and checking staleness."""
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)  # Ensure tables exist

        # Count SKUs
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pricing_cache WHERE provider = ?", (provider,))
        sku_count = cursor.fetchone()[0]

        # Get last refreshed timestamp
        cursor.execute(
            "SELECT value FROM metadata WHERE key = ?", (f"{provider}_last_refreshed_at",)
        )
        row = cursor.fetchone()

        last_refreshed_at = row[0] if row else None

        if not last_refreshed_at:
            return {
                "provider": provider,
                "last_refreshed_at": None,
                "age_hours": 999999.0,
                "sku_count": sku_count,
                "stale": True,
            }

        # Parse timestamp
        # Accept 'Z' suffix by replacing it with +00:00 (Python ISO standard format)
        ts_str = last_refreshed_at.replace("Z", "+00:00")
        refreshed_dt = datetime.fromisoformat(ts_str)
        now_dt = datetime.now(UTC)

        delta = now_dt - refreshed_dt
        age_hours = delta.total_seconds() / 3600.0
        stale = age_hours > 72.0

        return {
            "provider": provider,
            "last_refreshed_at": last_refreshed_at,
            "age_hours": age_hours,
            "sku_count": sku_count,
            "stale": stale,
        }
    finally:
        conn.close()


def get_cached_price(
    db_path: str, provider: str, sku_id: str, region: str
) -> dict[str, Any] | None:
    """Retrieve the cached price details for a given SKU ID and Region."""
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sku_id, service, region, unit, unit_price, sku_group, description, snapshot_ts
            FROM pricing_cache
            WHERE provider = ? AND sku_id = ? AND region = ?
            """,
            (provider, sku_id, region),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "sku_id": row[0],
            "service": row[1],
            "region": row[2],
            "unit": row[3],
            "unit_price": row[4],
            "sku_group": row[5],
            "description": row[6],
            "snapshot_ts": row[7],
        }
    finally:
        conn.close()


def update_cache(
    db_path: str, provider: str, skus_list: list[dict[str, Any]], snapshot_ts: str
) -> None:
    """Atomically replace the cached SKU prices with a new set under a transaction."""
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        with conn:
            # Delete existing data for provider
            conn.execute("DELETE FROM pricing_cache WHERE provider = ?", (provider,))

            # Insert new records
            for s in skus_list:
                # This will raise KeyError if any field is missing, triggering a rollback
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pricing_cache (
                        provider, sku_id, service, region, unit,
                        unit_price, sku_group, description, snapshot_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        provider,
                        s["sku_id"],
                        s["service"],
                        s["region"],
                        s["unit"],
                        s["unit_price"],
                        s["sku_group"],
                        s.get("description", ""),
                        snapshot_ts,
                    ),
                )

            # Update metadata
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (f"{provider}_last_refreshed_at", snapshot_ts),
            )
    finally:
        conn.close()
