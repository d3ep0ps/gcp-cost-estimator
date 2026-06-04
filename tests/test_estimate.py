import pytest
from pydantic import ValidationError

from gcp_billing_mcp.core.estimate import Estimate, PricedLineItem


def test_estimate_serializes_with_required_fields() -> None:
    """Verify that a complete Estimate successfully serializes with required fields."""
    data = {
        "pricing_snapshot": "2026-06-01T00:00:00Z",
        "line_items": [
            {
                "resource_id": "vm-1",
                "sku_id": "GCP-SKU-123",
                "component": "vcpu",
                "unit_price": 0.0475,
                "unit": "hour",
                "qty": 4,
                "usage_hours": 730,
                "monthly_cost": 138.7,
            }
        ],
        "monthly_total": 138.7,
        "unpriced": [],
        "assumptions": ["Defaulted runtime to 730 hours/month."],
    }
    est = Estimate(**data)
    assert est.currency == "USD"
    assert est.monthly_total == 138.7
    assert len(est.line_items) == 1
    assert est.line_items[0].resource_id == "vm-1"
    assert est.line_items[0].sku_id == "GCP-SKU-123"


def test_line_item_requires_sku_id_and_unit() -> None:
    """Verify that a line item requires a sku_id and unit to parse."""
    # Missing sku_id
    with pytest.raises(ValidationError):
        PricedLineItem(
            resource_id="vm-1",
            component="vcpu",
            unit_price=0.0475,
            unit="hour",
            qty=4,
            usage_hours=730,
            monthly_cost=138.7,
        )

    # Missing unit
    with pytest.raises(ValidationError):
        PricedLineItem(
            resource_id="vm-1",
            sku_id="GCP-SKU-123",
            component="vcpu",
            unit_price=0.0475,
            qty=4,
            usage_hours=730,
            monthly_cost=138.7,
        )


def test_unpriced_list_present_even_when_empty() -> None:
    """Verify that unpriced is initialized to an empty list if not specified."""
    data = {
        "pricing_snapshot": "2026-06-01T00:00:00Z",
        "line_items": [],
        "monthly_total": 0.0,
    }
    est = Estimate(**data)
    assert est.unpriced == []
    assert est.assumptions == []
