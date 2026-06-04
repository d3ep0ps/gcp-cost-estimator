# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_gke_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static GKE SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/gke_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_gke_cluster_emits_management_fee_sku(populated_gke_db: str) -> None:
    """Verify that GKE cluster maps to management fee SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"enable_autopilot": False},
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    mgmt_map = next(m for m in mappings if m["component"] == "management_fee")
    assert mgmt_map["sku_id"] == "SKU-GKE-MGMT-USC1"
    assert mgmt_map["unit_price"] == 0.10
    assert mgmt_map["unit"] == "h"


def test_gke_cluster_management_fee_qty_is_runtime_hours(populated_gke_db: str) -> None:
    """Verify that GKE cluster management fee quantity corresponds to runtime hours."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={"enable_autopilot": False},
        usage={"runtime_hours_per_month": 500.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    mgmt_map = next(m for m in mappings if m["component"] == "management_fee")
    # For quantity 1 cluster and 500 hours, qty is 500.0
    assert mgmt_map["qty"] == 500.0


def test_gke_cluster_with_nodes_emits_vcpu_ram_and_disk_skus(populated_gke_db: str) -> None:
    """Verify GKE cluster with nodes decomposes into CPU, RAM, and disk SKUs."""
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
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Expected: management_fee + CPU + RAM + Disk = 4 mappings
    assert len(mappings) == 4

    cpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert cpu_map["sku_id"] == "SKU-E2-CPU-USC1"
    assert cpu_map["qty"] == 12.0  # 4 vCPUs * 3 nodes

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SKU-E2-RAM-USC1"
    assert ram_map["qty"] == 48.0  # 16 GB * 3 nodes

    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-PD-USC1"
    assert disk_map["qty"] == 300.0  # 100 GB * 3 nodes


def test_gke_cluster_no_machine_type_emits_management_fee_only(populated_gke_db: str) -> None:
    """Verify GKE cluster without machine type only emits management fee."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={},
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["component"] == "management_fee"


def test_gke_node_pool_emits_vcpu_ram_disk_skus_for_all_nodes(populated_gke_db: str) -> None:
    """Verify GKE node pool maps to CPU, RAM, disk SKUs but NO management fee."""
    resource = Resource(
        provider="gcp",
        resource_id="pool-1",
        service="container",
        kind="gke_node_pool",
        region="us-central1",
        attributes={
            "machine_type": "e2-standard-4",
            "node_count": 2,
            "disk_size_gb": 150,
            "disk_type": "pd-ssd",
        },
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Expected: CPU + RAM + Disk = 3 mappings (NO management fee)
    assert len(mappings) == 3

    assert not any(m["component"] == "management_fee" for m in mappings)

    cpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert cpu_map["sku_id"] == "SKU-E2-CPU-USC1"
    assert cpu_map["qty"] == 8.0  # 4 vCPUs * 2 nodes

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SKU-E2-RAM-USC1"
    assert ram_map["qty"] == 32.0  # 16 GB * 2 nodes

    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-SSD-USC1"
    assert disk_map["qty"] == 300.0  # 150 GB * 2 nodes


def test_gke_node_count_multiplies_vcpu_and_ram_qty(populated_gke_db: str) -> None:
    """Verify that node count acts as multiplier for resources."""
    resource = Resource(
        provider="gcp",
        resource_id="pool-1",
        service="container",
        kind="gke_node_pool",
        region="us-central1",
        attributes={
            "machine_type": "e2-standard-4",
            "node_count": 10,
            "disk_size_gb": 100,
        },
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    cpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert cpu_map["qty"] == 40.0  # 4 vCPU * 10 nodes


def test_gke_disk_type_pd_ssd_maps_to_ssd_sku(populated_gke_db: str) -> None:
    """Verify that pd-ssd GKE disk maps to SSD SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="pool-1",
        service="container",
        kind="gke_node_pool",
        region="us-central1",
        attributes={
            "machine_type": "e2-standard-4",
            "node_count": 1,
            "disk_size_gb": 100,
            "disk_type": "pd-ssd",
        },
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-SSD-USC1"


def test_gke_disk_type_pd_standard_maps_to_standard_sku(populated_gke_db: str) -> None:
    """Verify that pd-standard GKE disk maps to standard PD SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="pool-1",
        service="container",
        kind="gke_node_pool",
        region="us-central1",
        attributes={
            "machine_type": "e2-standard-4",
            "node_count": 1,
            "disk_size_gb": 100,
            "disk_type": "pd-standard",
        },
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-PD-USC1"


def test_gke_unresolvable_machine_type_reported_unpriced(populated_gke_db: str) -> None:
    """Verify that unresolvable machine type is reported as unpriced."""
    resource = Resource(
        provider="gcp",
        resource_id="pool-1",
        service="container",
        kind="gke_node_pool",
        region="us-central1",
        attributes={
            "machine_type": "invalid-machine-type",
            "node_count": 1,
        },
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "unknown machine_type" in unpriced[0]["reason"].lower()


def test_gke_management_fee_always_present_even_with_zero_nodes(populated_gke_db: str) -> None:
    """Verify that GKE cluster always emits management fee SKU even if node count is 0."""
    resource = Resource(
        provider="gcp",
        resource_id="gke-1",
        service="container",
        kind="gke_cluster",
        region="us-central1",
        attributes={
            "node_count": 0,
        },
        usage={"runtime_hours_per_month": 730.0},
    )
    mapper = GcpSkuMapper(populated_gke_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["component"] == "management_fee"
