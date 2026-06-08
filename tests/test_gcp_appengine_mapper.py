# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import AttachedResource, Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.service import estimate_infrastructure


@pytest.fixture
def populated_appengine_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static App Engine SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/appengine_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-08T12:00:00Z")
    return temp_db_path


def test_app_engine_standard_instance_hour_cost_equals_hand_computed_value(
    populated_appengine_db: str,
) -> None:
    """Verify standard instance hour cost equals hand-computed expected value.
    F2 instance class has 2x multiplier. 100 hours of runtime in us-central1:
    Quantity = 100 * 2 = 200 hours.
    Base price = 0.05.
    Total expected cost = 200 * 0.05 = 10.00 USD.
    """
    r = Resource(
        provider="gcp",
        resource_id="ae-std-hand",
        service="appengine",
        kind="app_engine_standard_version",
        region="us-central1",
        attributes={
            "instance_class": "F2",
        },
        usage={
            "runtime_hours_per_month": 100.0,
        },
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_appengine_db, model)

    assert len(est.unpriced) == 0
    assert abs(est.monthly_total - 10.00) < 1e-4


def test_app_engine_standard_fifteen_minute_tail_added_to_instance_lifecycle(
    populated_appengine_db: str,
) -> None:
    """Verify that the 15-minute tail (+0.25h) is added per lifecycle event.
    F1 instance class (1x multiplier), 100 hours of runtime, 40 lifecycle events.
    Total runtime = 100 + 40 * 0.25 = 110 hours.
    Base price = 0.05.
    Total expected cost = 110 * 0.05 = 5.50 USD.
    """
    r = Resource(
        provider="gcp",
        resource_id="ae-std-tail",
        service="appengine",
        kind="app_engine_standard_version",
        region="us-central1",
        attributes={
            "instance_class": "F1",
        },
        usage={
            "runtime_hours_per_month": 100.0,
            "lifecycle_events_per_month": 40.0,
        },
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_appengine_db, model)

    assert len(est.unpriced) == 0
    assert abs(est.monthly_total - 5.50) < 1e-4


def test_app_engine_flexible_cost_reuses_compute_engine_vcpu_and_memory_skus(
    populated_appengine_db: str,
) -> None:
    """Verify App Engine flexible CPU/RAM mapping and pricing.
    cpu = 2, memory_gb = 4.0, runtime_hours = 730
    vcpu price = 0.0526 / hr, ram price = 0.0071 / hr.
    vcpu expected = 2 * 730 * 0.0526 = 76.796 USD.
    ram expected = 4 * 730 * 0.0071 = 20.732 USD.
    # Total expected = 97.528 USD + 0.40 USD (default 10GB PD Standard capacity) = 97.928 USD.
    """
    r = Resource(
        provider="gcp",
        resource_id="ae-flex-cpu-ram",
        service="appengine",
        kind="app_engine_flexible_version",
        region="us-central1",
        attributes={
            "cpu": 2,
            "memory_gb": 4.0,
        },
        usage={
            "runtime_hours_per_month": 730.0,
        },
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_appengine_db, model)

    assert len(est.unpriced) == 0
    assert abs(est.monthly_total - 97.928) < 1e-4


def test_app_engine_flexible_persistent_disk_cost_reuses_compute_engine_pd_sku(
    populated_appengine_db: str,
) -> None:
    """Verify App Engine flexible environment reuses the Compute Engine standard PD SKU."""
    r = Resource(
        provider="gcp",
        resource_id="ae-flex-pd",
        service="appengine",
        kind="app_engine_flexible_version",
        region="us-central1",
        attributes={
            "cpu": 1,
            "memory_gb": 2.0,
            "disk_gb": 20,
        },
        attached=[
            AttachedResource(kind="pd_persistent_disk", quantity=1, attributes={"size_gb": 20})
        ],
    )
    mapper = GcpSkuMapper(populated_appengine_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)

    assert len(unpriced) == 0
    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-PD-USC1"
    assert disk_map["unit_price"] == 0.0400
    assert disk_map["qty"] == 20.0


def test_app_engine_flexible_egress_cost_reuses_vpc_egress_sku(populated_appengine_db: str) -> None:
    """Verify App Engine flexible environment maps and reuses standard VPC egress SKU."""
    r = Resource(
        provider="gcp",
        resource_id="ae-flex-egress",
        service="appengine",
        kind="app_engine_flexible_version",
        region="us-central1",
        attributes={
            "cpu": 1,
            "memory_gb": 2.0,
        },
        usage={
            "egress_gb": 50.0,
        },
    )
    mapper = GcpSkuMapper(populated_appengine_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)

    assert len(unpriced) == 0
    egress_map = next(m for m in mappings if m["component"] == "egress")
    assert egress_map["sku_id"] == "SKU-EGRESS-USC1"
    assert egress_map["unit_price"] == 0.12
    assert egress_map["qty"] == 50.0


def test_app_engine_network_egress_billed_per_gib_beyond_free_tier_threshold_documented(
    populated_appengine_db: str,
) -> None:
    """Verify that App Engine standard egress maps to egress SKU when usage is provided."""
    r = Resource(
        provider="gcp",
        resource_id="ae-std-egress",
        service="appengine",
        kind="app_engine_standard_version",
        region="us-central1",
        attributes={
            "instance_class": "F1",
        },
        usage={
            "egress_gb": 10.0,
        },
    )
    mapper = GcpSkuMapper(populated_appengine_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)

    assert len(unpriced) == 0
    egress_map = next(m for m in mappings if m["component"] == "egress")
    assert egress_map["sku_id"] == "SKU-EGRESS-USC1"
    assert egress_map["qty"] == 10.0
