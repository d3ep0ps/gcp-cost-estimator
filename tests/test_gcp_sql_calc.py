import json

import pytest

from gcp_billing_mcp.core.calc import calculate_line_items, calculate_totals


def test_cloud_sql_cost_cases_match_known_answers() -> None:
    """Verify that Cloud SQL instance cost calculations match hand-computed known answers."""
    from pathlib import Path

    with Path("tests/fixtures/cloud_sql_cost_cases.json").open() as f:
        cases = json.load(f)

    for case in cases:
        label = case["label"]
        vcpu = case["vcpu"]
        ram_gb = case["ram_gb"]
        disk_gb = case["disk_gb"]
        ha_mult = case["ha_mult"]

        vcpu_price = case["vcpu_price_per_hour"]
        ram_price = case["ram_price_per_gib_hour"]
        ssd_price = case["ssd_price_per_gb_month"]

        # Reconstruct mappings output by SkuMapper for the test case
        mappings = [
            {
                "sku_id": "CPU-SKU",
                "component": "vcpu",
                "unit": "h",
                "unit_price": vcpu_price,
                "qty": float(vcpu) * ha_mult,
            },
            {
                "sku_id": "RAM-SKU",
                "component": "ram",
                "unit": "GiBy.mo",  # Test converting ram unit 'GiBy.mo' which is month-based in unit rates
                "unit_price": ram_price
                * 730.0,  # convert hourly ram price back to monthly for GiBy.mo
                "qty": float(ram_gb) * ha_mult,
            },
            {
                "sku_id": "SSD-SKU",
                "component": "storage",
                "unit": "GiBy.mo",
                "unit_price": ssd_price,
                "qty": float(disk_gb),
            },
        ]

        usage = {"runtime_hours_per_month": 730.0}
        line_items = calculate_line_items("db-test", mappings, usage)

        # Verify component costs
        vcpu_item = next(item for item in line_items if item.component == "vcpu")
        assert pytest.approx(vcpu_item.monthly_cost, abs=1e-2) == case["expected_vcpu_cost"], (
            f"{label}: CPU cost mismatch"
        )

        ram_item = next(item for item in line_items if item.component == "ram")
        assert pytest.approx(ram_item.monthly_cost, abs=1e-2) == case["expected_ram_cost"], (
            f"{label}: RAM cost mismatch"
        )

        storage_item = next(item for item in line_items if item.component == "storage")
        assert (
            pytest.approx(storage_item.monthly_cost, abs=1e-2) == case["expected_storage_cost"]
        ), f"{label}: Storage cost mismatch"

        total_cost = calculate_totals(line_items)
        assert pytest.approx(total_cost, abs=1e-2) == case["expected_monthly_total"], (
            f"{label}: Total cost mismatch"
        )


def test_cloud_sql_sqlserver_license_scaling_with_hours() -> None:
    """Verify that SQL Server license hourly cost scales with usage hours."""
    mappings = [
        {
            "sku_id": "SQL-LICENSE-SKU",
            "component": "license",
            "unit": "h",
            "unit_price": 0.1644,
            "qty": 4.0,  # 4 vCPUs license
        }
    ]
    usage = {"runtime_hours_per_month": 365.0}  # Half month

    line_items = calculate_line_items("db-1", mappings, usage)
    assert len(line_items) == 1
    assert line_items[0].component == "license"
    assert round(line_items[0].monthly_cost, 4) == round(0.1644 * 4.0 * 365.0, 4)
    assert line_items[0].usage_hours == 365.0
