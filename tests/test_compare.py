# SPDX-License-Identifier: Apache-2.0

import sqlite3

import pytest

from gcp_billing_mcp.core.compare import (
    compare_estimates,
    compare_regions,
    find_unpriced,
    suggest_cheaper_machine_types,
    what_if,
)
from gcp_billing_mcp.core.estimate import Estimate
from gcp_billing_mcp.core.model import Resource, ResourceModel
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache


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
    from gcp_billing_mcp.core.estimate import PricedLineItem

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


def test_suggest_returns_same_or_more_vcpu_ram_at_lower_price(populated_db: str) -> None:
    """Verify that suggest_cheaper_machine_types recommends cheaper viable configurations."""
    # current: n2-standard-4 (4 vcpu, 16gb ram)
    # CPU price: 0.0475
    # Let's add standard-4 CPU at 0.0475, but standard-2 CPU is at 0.0475 too, wait.
    # To test suggestions, let's make sure the suggestions logic returns correct list.
    resource = Resource(
        provider="gcp",
        resource_id="vm-1",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
        usage={"runtime_hours_per_month": 730.0},
    )

    # Let's mock resolve_machine_type_specs to make sure candidate specs match/exceed.
    # We want to ensure that suggestions returns cheaper alternatives.
    # n2-standard-4 has 4 vcpu / 16gb. e2-standard-4 has 4 vcpu / 16gb.
    # Let's add e2-standard-4 CPU and RAM SKUs to populated_db fixture or manually here.
    conn = sqlite3.connect(populated_db)
    query = (
        "INSERT INTO pricing_cache "
        "(provider, sku_id, service, region, unit, "
        "unit_price, sku_group, description, snapshot_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    conn.execute(
        query,
        (
            "gcp",
            "SKU-E2-CPU",
            "compute",
            "us-central1",
            "h",
            0.0252,
            "CPU",
            "E2 Instance Core",
            "2026-06-03T12:00:00Z",
        ),
    )
    conn.execute(
        query,
        (
            "gcp",
            "SKU-E2-RAM",
            "compute",
            "us-central1",
            "GiBy.mo",
            0.0033,
            "RAM",
            "E2 Instance Ram",
            "2026-06-03T12:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    suggestions = suggest_cheaper_machine_types(populated_db, resource)
    assert len(suggestions) > 0
    # E2 standard-4 should be suggested as it's cheaper and matches specs (4 vcpu, 16gb ram)
    e2_spec = next((s for s in suggestions if "e2-standard-4" in s["machine_type"]), None)
    assert e2_spec is not None
    assert e2_spec["vcpu"] == 4
    assert e2_spec["ram_gb"] == 16.0
    assert e2_spec["monthly_savings"] > 0.0


def test_suggest_never_recommends_under_spec(populated_db: str) -> None:
    """Verify that suggestions never suggest machine types with fewer vCPUs or less RAM."""
    resource = Resource(
        provider="gcp",
        resource_id="vm-1",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
        usage={"runtime_hours_per_month": 730.0},
    )
    suggestions = suggest_cheaper_machine_types(populated_db, resource)
    for s in suggestions:
        assert s["vcpu"] >= 4
        assert s["ram_gb"] >= 16.0


def test_find_unpriced_lists_gaps_before_estimate(populated_db: str) -> None:
    """Verify that find_unpriced successfully identifies unsupported or unmapped resources."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "unknown-machine-999"},
            },
            {
                "provider": "gcp",
                "resource_id": "topic-1",
                "service": "pubsub",
                "kind": "google_pubsub_topic",
                "region": "us-central1",
            },
        ]
    }
    model = ResourceModel(**data)
    unpriced = find_unpriced(populated_db, model)
    assert len(unpriced) >= 2

    reasons = [up["reason"].lower() for up in unpriced]
    assert any("unknown machine_type" in r for r in reasons)
    assert any("unsupported resource kind" in r or "unmapped" in r for r in reasons)


def test_suggest_sql_tier_returns_cheaper_custom(temp_db_path: str) -> None:
    """Verify suggest_cheaper_machine_types handles Cloud SQL instances and suggests cheaper tiers."""
    import json
    from pathlib import Path
    from unittest.mock import patch

    from gcp_billing_mcp.core.estimate import Estimate

    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/cloud_sql_skus.json").open() as f:
        mock_skus = json.load(f)

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")

    resource = Resource(
        provider="gcp",
        resource_id="db-1",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-8-30720",  # 8 vCPU, 30 GB RAM
            "edition": "ENTERPRISE",
            "database_version": "MYSQL_8_0",
            "availability_type": "ZONAL",
        },
    )

    def mock_estimate_infra(_db_path, model):
        res = model.resources[0]
        tier = res.attributes.get("tier", "")
        if tier == "db-custom-8-30720":
            return Estimate(
                pricing_snapshot="2026-06-03",
                line_items=[],
                monthly_total=500.0,
                unpriced=[],
                assumptions=[],
            )
        if tier == "db-custom-16-30720":
            return Estimate(
                pricing_snapshot="2026-06-03",
                line_items=[],
                monthly_total=300.0,
                unpriced=[],
                assumptions=[],
            )
        return Estimate(
            pricing_snapshot="2026-06-03",
            line_items=[],
            monthly_total=1000.0,
            unpriced=[],
            assumptions=[],
        )

    with patch(
        "gcp_billing_mcp.core.compare.estimate_infrastructure", side_effect=mock_estimate_infra
    ):
        suggestions = suggest_cheaper_machine_types(temp_db_path, resource)

    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug["tier"] == "db-custom-16-30720"
    assert sug["vcpu"] == 16
    assert sug["ram_gb"] == 30.0
    assert sug["monthly_cost"] == 300.0
    assert sug["monthly_savings"] == 200.0
