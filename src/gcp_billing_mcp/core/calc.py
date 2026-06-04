from typing import Any

from gcp_billing_mcp.core.estimate import PricedLineItem


def calculate_line_items(
    resource_id: str, mappings: list[dict[str, Any]], usage: dict[str, Any]
) -> list[PricedLineItem]:
    """Calculate the individual monthly costs for each billable SKU mapped to a resource.

    Adjusts vCPU and RAM costs by VM runtime hours, while storage/disks are billed monthly.
    """
    usage_hours = float(usage.get("runtime_hours_per_month", 730.0))
    line_items: list[PricedLineItem] = []

    for mapping in mappings:
        sku_id = mapping["sku_id"]
        component = mapping["component"]
        unit = mapping["unit"]
        unit_price = mapping["unit_price"]
        qty = mapping["qty"]

        # CPU, RAM, and license costs scale with active runtime hours
        if component in ("vcpu", "ram", "license"):
            if "h" in unit.lower() or "hour" in unit.lower():
                monthly_cost = unit_price * qty * usage_hours
                item_hours = usage_hours
            elif "mo" in unit.lower() or "month" in unit.lower():
                # Convert monthly rate (like GiBy.mo) to hourly rate using 730 hours average
                monthly_cost = (unit_price / 730.0) * qty * usage_hours
                item_hours = usage_hours
            else:
                # Default fallback
                monthly_cost = unit_price * qty * usage_hours
                item_hours = usage_hours
        else:
            # Storage/continuous components are billed monthly, independent of runtime hours
            monthly_cost = unit_price * qty
            item_hours = 730.0  # Represents a full month of continuous storage presence

        line_items.append(
            PricedLineItem(
                resource_id=resource_id,
                sku_id=sku_id,
                component=component,
                unit_price=unit_price,
                unit=unit,
                qty=qty,
                usage_hours=item_hours,
                monthly_cost=monthly_cost,
            )
        )

    return line_items


def calculate_totals(items: list[PricedLineItem]) -> float:
    """Sum up the monthly costs of all priced line items."""
    return sum(item.monthly_cost for item in items)
