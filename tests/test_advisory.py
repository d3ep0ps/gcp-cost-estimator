# SPDX-License-Identifier: Apache-2.0

import sqlite3
from unittest.mock import patch

import pytest

from gcp_cost_estimator.core.advisory import (
    find_unpriced,
    suggest_cheaper_machine_types,
)
from gcp_cost_estimator.core.estimate import Estimate
from gcp_cost_estimator.core.model import Resource, ResourceModel
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


def test_suggest_returns_same_or_more_vcpu_ram_at_lower_price(populated_db: str) -> None:
    """Verify that suggest_cheaper_machine_types recommends cheaper viable configurations."""
    # current: n2-standard-4 (4 vcpu, 16gb ram)
    resource = Resource(
        provider="gcp",
        resource_id="vm-1",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
        usage={"runtime_hours_per_month": 730.0},
    )

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
        "gcp_cost_estimator.core.advisory.estimate_infrastructure", side_effect=mock_estimate_infra
    ):
        suggestions = suggest_cheaper_machine_types(temp_db_path, resource)

    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug["tier"] == "db-custom-16-30720"
    assert sug["vcpu"] == 16
    assert sug["ram_gb"] == 30.0
    assert sug["monthly_cost"] == 300.0
    assert sug["monthly_savings"] == 200.0


def test_suggest_alloydb_smaller_cpu_count_at_lower_cost(temp_db_path: str) -> None:
    """Verify that we suggest cheaper AlloyDB configurations if they exist."""
    import json
    from pathlib import Path

    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/alloydb_skus.json").open() as f:
        mock_skus = json.load(f)
    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")

    resource = Resource(
        provider="gcp",
        resource_id="db-read-pool",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "READ_POOL",
            "cpu_count": 8,
            "node_count": 2,
        },
    )

    def mock_estimate_infra(_db_path, model):
        res = model.resources[0]
        cpu = int(res.attributes.get("cpu_count", 0))
        nodes = int(res.attributes.get("node_count", 1))
        if cpu == 8 and nodes == 2:
            return Estimate(
                pricing_snapshot="2026-06-03",
                line_items=[],
                monthly_total=500.0,
                unpriced=[],
                assumptions=[],
            )
        if cpu == 16 and nodes == 1:
            return Estimate(
                pricing_snapshot="2026-06-03",
                line_items=[],
                monthly_total=400.0,
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
        "gcp_cost_estimator.core.advisory.estimate_infrastructure", side_effect=mock_estimate_infra
    ):
        suggestions = suggest_cheaper_machine_types(temp_db_path, resource)

    assert len(suggestions) > 0
    sug = next(s for s in suggestions if s["cpu_count"] == 16 and s["node_count"] == 1)
    assert sug["monthly_cost"] == 400.0
    assert sug["monthly_savings"] == 100.0


def test_suggest_alloydb_never_recommends_under_spec(temp_db_path: str) -> None:
    """Verify suggestions never recommend AlloyDB configurations under capacity."""
    resource = Resource(
        provider="gcp",
        resource_id="db-read-pool",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "READ_POOL",
            "cpu_count": 8,
            "node_count": 2,
        },
    )

    def mock_estimate_infra(_db_path, _model):
        return Estimate(
            pricing_snapshot="2026-06-03",
            line_items=[],
            monthly_total=10.0,
            unpriced=[],
            assumptions=[],
        )

    with patch(
        "gcp_cost_estimator.core.advisory.estimate_infrastructure", side_effect=mock_estimate_infra
    ):
        suggestions = suggest_cheaper_machine_types(temp_db_path, resource)

    for s in suggestions:
        assert s["cpu_count"] * s["node_count"] >= 16


def test_suggest_alloydb_read_pool_considers_total_capacity(temp_db_path: str) -> None:
    """Verify read pool suggestions check total capacity (cpu * nodes)."""
    resource = Resource(
        provider="gcp",
        resource_id="db-read-pool",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "READ_POOL",
            "cpu_count": 4,
            "node_count": 2,
        },
    )

    def mock_estimate_infra(_db_path, _model):
        return Estimate(
            pricing_snapshot="2026-06-03",
            line_items=[],
            monthly_total=10.0,
            unpriced=[],
            assumptions=[],
        )

    with patch(
        "gcp_cost_estimator.core.advisory.estimate_infrastructure", side_effect=mock_estimate_infra
    ):
        suggestions = suggest_cheaper_machine_types(temp_db_path, resource)

    for s in suggestions:
        assert s["cpu_count"] * s["node_count"] >= 8


def test_suggest_alloydb_no_option_returns_empty_list(temp_db_path: str) -> None:
    """Verify suggest returns empty if no cheaper option exists."""
    resource = Resource(
        provider="gcp",
        resource_id="db-read-pool",
        service="alloydb",
        kind="alloydb_instance",
        region="us-central1",
        attributes={
            "instance_type": "READ_POOL",
            "cpu_count": 8,
            "node_count": 2,
        },
    )

    def mock_estimate_infra(_db_path, model):
        res = model.resources[0]
        cpu = int(res.attributes.get("cpu_count", 0))
        nodes = int(res.attributes.get("node_count", 1))
        if cpu == 8 and nodes == 2:
            return Estimate(
                pricing_snapshot="2026-06-03",
                line_items=[],
                monthly_total=10.0,
                unpriced=[],
                assumptions=[],
            )
        return Estimate(
            pricing_snapshot="2026-06-03",
            line_items=[],
            monthly_total=100.0,
            unpriced=[],
            assumptions=[],
        )

    with patch(
        "gcp_cost_estimator.core.advisory.estimate_infrastructure", side_effect=mock_estimate_infra
    ):
        suggestions = suggest_cheaper_machine_types(temp_db_path, resource)

    assert len(suggestions) == 0
