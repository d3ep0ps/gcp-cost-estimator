# SPDX-License-Identifier: Apache-2.0

import contextlib
import json
import os
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_mcp_sql_integration_e2e(temp_db_path: str) -> None:
    """E2E integration test that uses the MCP client to call the server.

    It sets a clean temporary database, runs `refresh_pricing_cache` to fetch
    real pricing data from the Google Cloud Billing API, estimates a Cloud SQL
    resource using the fetched prices, and verifies the output.
    """
    # Inherit existing environment variables (such as credentials) and override the DB path
    env = os.environ.copy()
    env["GCP_BILLING_DB_PATH"] = temp_db_path

    # Configure the server to log to a temporary log file so we can inspect its API calls
    temp_log_path = Path(temp_db_path).parent / "temp_mcp.log"
    with contextlib.suppress(OSError):
        temp_log_path.unlink(missing_ok=True)
    env["GCP_BILLING_LOG_FILE"] = str(temp_log_path)
    env["GCP_BILLING_LOG_LEVEL"] = "INFO"

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "gcp_billing_mcp.mcp.server"],
        env=env,
    )

    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        # 1. Force refresh cache (this calls the live Google Cloud Billing API)
        refresh_result = await session.call_tool(
            "refresh_pricing_cache", {"provider": "gcp", "force": True}
        )
        assert refresh_result is not None
        assert refresh_result.content is not None
        refresh_data = json.loads(refresh_result.content[0].text)
        assert refresh_data["status"] == "refreshed"
        assert refresh_data["sku_count"] > 0

        # 2. Estimate Cloud SQL Instance using the live prices
        test_model = {
            "resources": [
                {
                    "provider": "gcp",
                    "resource_id": "db-1",
                    "service": "sql",
                    "kind": "cloud_sql_instance",
                    "region": "us-central1",
                    "attributes": {
                        "tier": "db-custom-2-7680",
                        "edition": "ENTERPRISE",
                        "database_version": "MYSQL_8_0",
                        "availability_type": "ZONAL",
                        "disk_size_gb": 100,
                        "disk_type": "PD_SSD",
                    },
                }
            ]
        }

        estimate_result = await session.call_tool("estimate_infrastructure", {"model": test_model})
        assert estimate_result is not None
        estimate_data = json.loads(estimate_result.content[0].text)

        # 3. Assertions on the E2E Estimate
        assert estimate_data["monthly_total"] > 0.0
        assert len(estimate_data["unpriced"]) == 0
        assert len(estimate_data["line_items"]) == 3  # vcpu + ram + storage

        # Verify real SKU IDs and non-zero costs are mapped
        vcpu_item = next(
            item for item in estimate_data["line_items"] if item["component"] == "vcpu"
        )
        assert vcpu_item["sku_id"] is not None
        assert vcpu_item["unit_price"] > 0.0
        assert vcpu_item["monthly_cost"] > 0.0

        ram_item = next(item for item in estimate_data["line_items"] if item["component"] == "ram")
        assert ram_item["sku_id"] is not None
        assert ram_item["unit_price"] > 0.0
        assert ram_item["monthly_cost"] > 0.0

        storage_item = next(
            item for item in estimate_data["line_items"] if item["component"] == "storage"
        )
        assert storage_item["sku_id"] is not None
        assert storage_item["unit_price"] > 0.0
        assert storage_item["monthly_cost"] > 0.0

    # 4. Read server logs to prove real Google Billing API calls were made
    log_content = temp_log_path.read_text()
    assert "Fetching pricing SKUs from Google Billing API URL" in log_content
    # Assert both compute (6F81-5844-456A) and sql (9662-B51E-5089) endpoints were queried
    assert "services/6F81-5844-456A/skus" in log_content
    assert "services/9662-B51E-5089/skus" in log_content

    # Clean up temp log
    with contextlib.suppress(OSError):
        temp_log_path.unlink(missing_ok=True)
