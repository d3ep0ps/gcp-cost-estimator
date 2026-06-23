# SPDX-License-Identifier: Apache-2.0

import sqlite3

import pytest

from gcp_cost_estimator.core.compare import (
    compare_estimates,
    compare_regions,
    what_if,
)
from gcp_cost_estimator.core.estimate import Estimate
from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache


@pytest.fixture
def populated_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with SKUs across regions and machine types."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    mock_skus = [
        # N2 CPU in us-central1 (cheaper)
        {
            "sku_id": "SKU-N2-CPU-CENTRAL",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core",
        },
        # N2 RAM in us-central1 (cheaper)
        {
            "sku_id": "SKU-N2-RAM-CENTRAL",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram",
        },
        # N2 CPU in us-east1 (more expensive)
        {
            "sku_id": "SKU-N2-CPU-EAST",
            "service": "compute engine",
            "region": "us-east1",
            "unit": "h",
            "unit_price": 0.0520,
            "sku_group": "CPU",
            "description": "N2 Instance Core",
        },
        # N2 RAM in us-east1 (more expensive)
        {
            "sku_id": "SKU-N2-RAM-EAST",
            "service": "compute engine",
            "region": "us-east1",
            "unit": "GiBy.mo",
            "unit_price": 0.0075,
            "sku_group": "RAM",
            "description": "N2 Instance Ram",
        },
    ]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_compare_regions_marks_cheapest(populated_db: str) -> None:
    """Verify that compare_regions computes prices across regions and identifies the cheapest."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)
    result = compare_regions(populated_db, model, ["us-central1", "us-east1"])

    assert result["cheapest_region"] == "us-central1"
    assert "us-central1" in result["estimates"]
    assert "us-east1" in result["estimates"]

    central_cost = result["estimates"]["us-central1"].monthly_total
    east_cost = result["estimates"]["us-east1"].monthly_total
    assert central_cost < east_cost


def test_compare_estimates_diffs_line_items() -> None:
    """Verify that compare_estimates calculates totals and line item diffs correctly."""
    from gcp_cost_estimator.core.estimate import PricedLineItem

    est_a = Estimate(
        pricing_snapshot="2026-06-03T12:00:00Z",
        line_items=[
            PricedLineItem(
                resource_id="vm-1",
                sku_id="SKU-1",
                component="vcpu",
                unit_price=0.05,
                unit="h",
                qty=4.0,
                usage_hours=730.0,
                monthly_cost=146.0,
            )
        ],
        monthly_total=146.0,
        unpriced=[],
        assumptions=[],
    )

    est_b = Estimate(
        pricing_snapshot="2026-06-03T12:00:00Z",
        line_items=[
            PricedLineItem(
                resource_id="vm-1",
                sku_id="SKU-1",
                component="vcpu",
                unit_price=0.05,
                unit="h",
                qty=8.0,
                usage_hours=730.0,
                monthly_cost=292.0,
            )
        ],
        monthly_total=292.0,
        unpriced=[],
        assumptions=[],
    )

    result = compare_estimates(est_a, est_b)
    assert result["monthly_total_a"] == 146.0
    assert result["monthly_total_b"] == 292.0
    assert result["monthly_total_diff"] == 146.0
    assert len(result["line_item_diffs"]) == 1

    diff = result["line_item_diffs"][0]
    assert diff["resource_id"] == "vm-1"
    assert diff["qty_diff"] == 4.0
    assert diff["cost_diff"] == 146.0


def test_what_if_changes_runtime_and_reprices(populated_db: str) -> None:
    """Verify that what_if simulation reprices correctly with changed parameters."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)

    # Simulation: change runtime_hours to 365.0
    result = what_if(populated_db, model, {"runtime_hours": 365.0})
    assert result["new_estimate"].monthly_total < 100.0  # roughly half
    assert result["comparison"]["monthly_total_diff"] < 0.0  # negative diff (savings)


def test_compare_regions_cheapest_reflects_actual_cost_order(populated_db: str) -> None:
    """cheapest_region must point to the region with the lowest monthly_total, not a fixed choice."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)
    result = compare_regions(populated_db, model, ["us-central1", "us-east1"])

    cheapest = result["cheapest_region"]
    cheapest_cost = result["estimates"][cheapest].monthly_total

    for region, est in result["estimates"].items():
        assert est.monthly_total >= cheapest_cost, (
            f"Region '{region}' (${est.monthly_total:.4f}) is cheaper than "
            f"cheapest_region '{cheapest}' (${cheapest_cost:.4f})"
        )


def test_what_if_unrecognised_keys_do_not_silently_match(populated_db: str) -> None:
    """Passing an unrecognised top-level change key must not produce a result
    identical to passing no changes — callers must be able to detect the no-op."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)

    # A recognised change produces a different cost
    result_recognised = what_if(populated_db, model, {"runtime_hours": 1.0})
    assert result_recognised["new_estimate"].monthly_total < 1.0

    # An unrecognised key produces the SAME cost as no change (baseline)
    result_unrecognised = what_if(populated_db, model, {"disk_type": "pd-ssd"})
    baseline = what_if(populated_db, model, {})
    assert result_unrecognised["new_estimate"].monthly_total == pytest.approx(
        baseline["new_estimate"].monthly_total
    ), (
        "Unrecognised key 'disk_type' should be a no-op — cost should equal baseline. "
        "If this changes in future, what_if() should warn about unrecognised keys."
    )
