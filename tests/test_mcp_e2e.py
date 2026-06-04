# SPDX-License-Identifier: Apache-2.0

import json

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_mcp_server_e2e() -> None:
    """End-to-End integration test for the GCP Billing MCP Server.

    Launches the server via stdio client, connects to it, and runs
    real pricing estimates and queries against the local database cache.
    """
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "gcp_billing_mcp.mcp.server"],
    )

    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        # 1. Verify Cache Status
        cache_status_result = await session.call_tool("get_cache_status", {"provider": "gcp"})
        assert cache_status_result is not None
        assert cache_status_result.content is not None

        # FastMCP returns text representation in content list, and raw value in data/result (if using new SDK)
        # FastMCP returns a structure containing a 'text' element. Let's parse it.
        text_content = cache_status_result.content[0].text
        status_data = json.loads(text_content)
        assert "sku_count" in status_data
        assert status_data["sku_count"] > 0
        assert status_data["stale"] is False

        # 2. Verify Resource model schema
        schema_result = await session.read_resource("schema://resource-model")
        assert schema_result is not None
        assert len(schema_result.contents) > 0
        assert "properties" in schema_result.contents[0].text

        # 3. Verify Estimate Infrastructure
        test_model = {
            "resources": [
                {
                    "provider": "gcp",
                    "resource_id": "n2-instance-1",
                    "service": "compute",
                    "kind": "gce_instance",
                    "region": "us-central1",
                    "attributes": {"machine_type": "n2-standard-4"},
                    "attached": [
                        {
                            "kind": "ssd_persistent_disk",
                            "quantity": 1,
                            "attributes": {"size_gb": 200},
                        }
                    ],
                }
            ]
        }

        estimate_result = await session.call_tool("estimate_infrastructure", {"model": test_model})
        assert estimate_result is not None
        estimate_data = json.loads(estimate_result.content[0].text)
        assert estimate_data["monthly_total"] > 0.0
        assert len(estimate_data["line_items"]) >= 3  # vcpu + ram + storage
        assert len(estimate_data["unpriced"]) == 0

        # Verify line items have correct SKU mapping details
        vcpu_item = next(
            item for item in estimate_data["line_items"] if item["component"] == "vcpu"
        )
        assert vcpu_item["unit_price"] > 0.0
        assert vcpu_item["qty"] == 4.0  # n2-standard-4 has 4 vCPUs

        ram_item = next(item for item in estimate_data["line_items"] if item["component"] == "ram")
        assert ram_item["unit_price"] > 0.0
        assert ram_item["qty"] == 16.0  # n2-standard-4 has 16 GB RAM

        storage_item = next(
            item for item in estimate_data["line_items"] if item["component"] == "storage"
        )
        assert storage_item["unit_price"] > 0.0
        assert storage_item["qty"] == 200.0  # 200 GB

        # 4. Compare Regions E2E
        compare_regions_result = await session.call_tool(
            "compare_regions", {"model": test_model, "regions": ["us-central1", "europe-west1"]}
        )
        assert compare_regions_result is not None
        compare_regions_data = json.loads(compare_regions_result.content[0].text)
        assert "cheapest_region" in compare_regions_data
        assert "us-central1" in compare_regions_data["estimates"]
        assert "europe-west1" in compare_regions_data["estimates"]

        # 5. Suggest Cheaper Machine Types E2E
        test_resource = test_model["resources"][0]
        suggest_result = await session.call_tool(
            "suggest_cheaper_machine_types", {"resource": test_resource}
        )
        assert suggest_result is not None
        suggest_list = [json.loads(c.text) for c in suggest_result.content]
        assert isinstance(suggest_list, list)
        assert len(suggest_list) > 0  # We expect at least e2-standard-4 as a cheaper option

        # 6. Render Estimate Markdown E2E
        render_result = await session.call_tool(
            "render_estimate", {"estimate": estimate_data, "format": "markdown"}
        )
        assert render_result is not None
        markdown_text = render_result.content[0].text
        assert "TOTAL" in markdown_text
        assert "Monthly Cost" in markdown_text
        assert "$" in markdown_text


async def run_standalone_e2e() -> None:
    """Helper method to run the E2E E2E check outside pytest, producing a pretty output report."""
    print("==================================================")
    print("Starting End-to-End GCP Billing MCP Server Test...")
    print("==================================================")

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "gcp_billing_mcp.mcp.server"],
    )

    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        print("[1/6] Connecting to server and initializing session...")
        await session.initialize()
        print("      Initialized successfully!")

        print("[2/6] Querying cache status...")
        cache_status_result = await session.call_tool("get_cache_status", {"provider": "gcp"})
        status_data = json.loads(cache_status_result.content[0].text)
        print(f"      Cache SKU Count: {status_data['sku_count']}")
        print(f"      Cache Last Refreshed: {status_data['last_refreshed_at']}")
        print(f"      Cache Stale Status: {status_data['stale']}")

        print("[3/6] Estimating cost for a VM (n2-standard-4 in us-central1 with 200GB SSD)...")
        test_model = {
            "resources": [
                {
                    "provider": "gcp",
                    "resource_id": "n2-instance-1",
                    "service": "compute",
                    "kind": "gce_instance",
                    "region": "us-central1",
                    "attributes": {"machine_type": "n2-standard-4"},
                    "attached": [
                        {
                            "kind": "ssd_persistent_disk",
                            "quantity": 1,
                            "attributes": {"size_gb": 200},
                        }
                    ],
                }
            ]
        }
        estimate_result = await session.call_tool("estimate_infrastructure", {"model": test_model})
        estimate_data = json.loads(estimate_result.content[0].text)
        print(f"      Estimated Monthly Cost: ${estimate_data['monthly_total']:.2f}")
        print("      Itemized cost breakdown:")
        for item in estimate_data["line_items"]:
            print(
                f"      - {item['component']}: {item['qty']} units @ ${item['unit_price']:.4f}/{item['unit']} = ${item['monthly_cost']:.2f}"
            )

        print("[4/6] Comparing us-central1 vs europe-west1...")
        compare_regions_result = await session.call_tool(
            "compare_regions", {"model": test_model, "regions": ["us-central1", "europe-west1"]}
        )
        compare_regions_data = json.loads(compare_regions_result.content[0].text)
        print(f"      Cheapest Region: {compare_regions_data['cheapest_region']}")
        for reg, est in compare_regions_data["estimates"].items():
            print(f"      - {reg}: ${est['monthly_total']:.2f}/mo")

        print("[5/6] Suggesting cheaper machine types...")
        suggest_result = await session.call_tool(
            "suggest_cheaper_machine_types", {"resource": test_model["resources"][0]}
        )
        suggest_list = [json.loads(c.text) for c in suggest_result.content]
        print(f"      Found {len(suggest_list)} alternative suggestions:")
        for recommendation in suggest_list[:3]:
            # suggest_cheaper_machine_types returns objects with keys machine_type, vcpu, ram_gb, monthly_cost, monthly_savings
            print(
                f"      - {recommendation['machine_type']}: CPU={recommendation['vcpu']}, RAM={recommendation['ram_gb']}GB, Price/Mo=${recommendation['monthly_cost']:.2f} (Savings=${recommendation['monthly_savings']:.2f})"
            )

        print("[6/6] Generating Markdown formatted output...")
        render_result = await session.call_tool(
            "render_estimate", {"estimate": estimate_data, "format": "markdown"}
        )
        print("\nRendered Markdown Output:")
        print("--------------------------------------------------")
        print(render_result.content[0].text)
        print("--------------------------------------------------")

        print("\nAll End-to-End checks passed successfully!")


if __name__ == "__main__":
    import anyio

    anyio.run(run_standalone_e2e)
