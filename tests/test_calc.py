from gcp_billing_mcp.core.calc import calculate_line_items, calculate_totals


def test_hourly_sku_times_730h_equals_expected_monthly() -> None:
    """Verify that hourly rates are scaled up correctly by usage hours."""
    mappings = [
        {
            "sku_id": "SKU-CPU",
            "component": "vcpu",
            "unit": "h",
            "unit_price": 0.0475,
            "qty": 4.0,
        }
    ]
    usage = {"runtime_hours_per_month": 730.0}

    line_items = calculate_line_items("vm-1", mappings, usage)
    assert len(line_items) == 1
    assert line_items[0].resource_id == "vm-1"
    assert line_items[0].sku_id == "SKU-CPU"
    assert round(line_items[0].monthly_cost, 4) == round(0.0475 * 4.0 * 730.0, 4)
    assert line_items[0].usage_hours == 730.0


def test_storage_gb_month_units_converted() -> None:
    """Verify that RAM (GiBy.mo) converts hourly usage, while storage (GiBy.mo) is month-based."""
    mappings = [
        # RAM (billed when running, so converted to hourly using 730h)
        {
            "sku_id": "SKU-RAM",
            "component": "ram",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "qty": 16.0,
        },
        # Storage (billed monthly, independent of runtime)
        {
            "sku_id": "SKU-SSD",
            "component": "storage",
            "unit": "GiBy.mo",
            "unit_price": 0.1700,
            "qty": 100.0,
        },
    ]
    usage = {"runtime_hours_per_month": 365.0}  # Half month

    line_items = calculate_line_items("vm-1", mappings, usage)
    assert len(line_items) == 2

    # RAM is running-based: price * qty * (hours / 730)
    ram_item = next(item for item in line_items if item.component == "ram")
    assert round(ram_item.monthly_cost, 4) == round(0.0063 * 16.0 * (365.0 / 730.0), 4)
    assert ram_item.usage_hours == 365.0

    # Storage is month-based: price * qty
    storage_item = next(item for item in line_items if item.component == "storage")
    assert round(storage_item.monthly_cost, 4) == round(0.1700 * 100.0, 4)
    assert storage_item.usage_hours == 730.0  # Represents continuous monthly billing


def test_quantity_multiplies_correctly() -> None:
    """Verify that resource quantities scale costs correctly."""
    mappings = [
        {
            "sku_id": "SKU-CPU",
            "component": "vcpu",
            "unit": "h",
            "unit_price": 0.0475,
            "qty": 4.0,  # Quantity of vCPUs per VM
        }
    ]
    usage = {"runtime_hours_per_month": 730.0}

    # Check that individual VM cost is scaled
    line_items = calculate_line_items("vm-1", mappings, usage)
    assert len(line_items) == 1
    assert round(line_items[0].monthly_cost, 2) == 138.70


def test_total_equals_sum_of_line_items() -> None:
    """Verify that calculate_totals sums up all monthly costs correctly."""
    from gcp_billing_mcp.core.estimate import PricedLineItem

    items = [
        PricedLineItem(
            resource_id="vm-1",
            sku_id="SKU-1",
            component="vcpu",
            unit_price=0.0475,
            unit="h",
            qty=4.0,
            usage_hours=730.0,
            monthly_cost=138.7,
        ),
        PricedLineItem(
            resource_id="vm-1",
            sku_id="SKU-2",
            component="ram",
            unit_price=0.0063,
            unit="GiBy.mo",
            qty=16.0,
            usage_hours=730.0,
            monthly_cost=73.584,
        ),
    ]

    total = calculate_totals(items)
    assert total == 138.7 + 73.584
