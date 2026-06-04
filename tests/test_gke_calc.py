# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.calc import calculate_line_items, calculate_totals
from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_gke_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static GKE SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/gke_skus.json").open() as f:
        mock_skus = json.load(f)

    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]
    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_gke_cost_cases_math(populated_gke_db: str) -> None:
    """Verify that GKE cost calculations match hand-computed expected costs."""
    with Path("tests/fixtures/gke_cost_cases.json").open() as f:
        cases = json.load(f)

    # Filter out metadata
    cases = [c for c in cases if "label" in c]

    mapper = GcpSkuMapper(populated_gke_db)

    for case in cases:
        resource = Resource(
            provider="gcp",
            resource_id="gke-test",
            service="container",
            kind="gke_cluster",
            region=case["region"],
            attributes={
                "machine_type": case["machine_type"],
                "node_count": case["node_count"],
                "disk_size_gb": case["disk_size_gb"],
                "disk_type": case["disk_type"],
            },
            usage={"runtime_hours_per_month": case["runtime_hours_per_month"]},
        )

        mappings, unpriced = mapper.map_resource_to_skus(resource)
        assert len(unpriced) == 0

        line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
        total = calculate_totals(line_items)

        # Check total cost
        assert pytest.approx(total, abs=1e-4) == case["expected_total"]

        # Check management fee cost
        mgmt_item = next(item for item in line_items if item.component == "management_fee")
        assert pytest.approx(mgmt_item.monthly_cost, abs=1e-4) == case["expected_mgmt_cost"]

        if case["node_count"] > 0:
            # Check vcpu cost
            vcpu_item = next(item for item in line_items if item.component == "vcpu")
            assert pytest.approx(vcpu_item.monthly_cost, abs=1e-4) == case["expected_vcpu_cost"]

            # Check ram cost
            ram_item = next(item for item in line_items if item.component == "ram")
            assert pytest.approx(ram_item.monthly_cost, abs=1e-4) == case["expected_ram_cost"]

            # Check disk storage cost
            disk_item = next(item for item in line_items if item.component == "storage")
            assert pytest.approx(disk_item.monthly_cost, abs=1e-4) == case["expected_disk_cost"]


def test_gke_management_fee_0_10_per_hour_times_730h(populated_gke_db: str) -> None:
    """Verify GKE cluster management fee is exactly 0.10 * 730 = $73.00."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"node_count": 0},
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)
    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    mgmt_item = next(item for item in line_items if item.component == "management_fee")
    assert pytest.approx(mgmt_item.monthly_cost, abs=1e-4) == 73.00


def test_gke_node_vcpu_cost_times_node_count(populated_gke_db: str) -> None:
    """Verify GKE node vcpu cost is multiplied by node count and usage hours."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"machine_type": "e2-standard-4", "node_count": 5},
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)
    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    vcpu_item = next(item for item in line_items if item.component == "vcpu")
    # Expected vcpu quantity: 4 vcpus * 5 nodes = 20
    # Expected cost: 0.021811 * 20 * 730 = 318.4406
    assert pytest.approx(vcpu_item.monthly_cost, abs=1e-4) == 318.4406


def test_gke_node_ram_cost_times_node_count(populated_gke_db: str) -> None:
    """Verify GKE node ram cost is multiplied by node count and usage hours."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"machine_type": "e2-standard-4", "node_count": 5},
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)
    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    ram_item = next(item for item in line_items if item.component == "ram")
    # Expected ram quantity: 16 GB * 5 nodes = 80
    # Expected cost: 0.002923 * 80 * 730 = 170.7032
    assert pytest.approx(ram_item.monthly_cost, abs=1e-4) == 170.7032


def test_gke_node_disk_cost_not_multiplied_by_hours(populated_gke_db: str) -> None:
    """Verify GKE disk cost is NOT scaled by runtime hours."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={
            "machine_type": "e2-standard-4",
            "node_count": 3,
            "disk_size_gb": 100,
            "disk_type": "pd-standard",
        },
        # Half of the month
        usage={"runtime_hours_per_month": 365.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)
    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    disk_item = next(item for item in line_items if item.component == "storage")
    # Expected disk cost: 0.040 * 100 * 3 = $12.00 (not scaled down by 365.0 hours!)
    assert pytest.approx(disk_item.monthly_cost, abs=1e-4) == 12.00


def test_gke_total_equals_management_fee_plus_all_node_costs(populated_gke_db: str) -> None:
    """Verify GKE cluster total cost is equal to the sum of management fee, vcpu, ram, and disk costs."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={
            "machine_type": "e2-standard-4",
            "node_count": 3,
            "disk_size_gb": 100,
            "disk_type": "pd-standard",
        },
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)
    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    total = calculate_totals(line_items)

    mgmt = next(item.monthly_cost for item in line_items if item.component == "management_fee")
    vcpu = next(item.monthly_cost for item in line_items if item.component == "vcpu")
    ram = next(item.monthly_cost for item in line_items if item.component == "ram")
    disk = next(item.monthly_cost for item in line_items if item.component == "storage")

    assert pytest.approx(total, abs=1e-4) == (mgmt + vcpu + ram + disk)


def test_gke_zero_node_count_total_equals_management_fee_only(populated_gke_db: str) -> None:
    """Verify GKE cluster with zero nodes costs exactly the management fee."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"node_count": 0},
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)
    line_items = calculate_line_items(resource.resource_id, mappings, resource.usage)
    total = calculate_totals(line_items)

    assert pytest.approx(total, abs=1e-4) == 73.00
