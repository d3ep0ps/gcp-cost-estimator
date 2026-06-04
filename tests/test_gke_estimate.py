import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.service import estimate_infrastructure


@pytest.fixture
def populated_combined_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with GKE and GCE mock SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load GKE SKUs
    with Path("tests/fixtures/gke_skus.json").open() as f:
        gke_skus = json.load(f)
    gke_skus = [s for s in gke_skus if s["sku_id"] != "METADATA-CITATION"]

    # GCE mock SKUs (just to verify cross-compatibility, can reuse GKE mock SKUs which has standard CPU/RAM/Disk)
    update_cache(temp_db_path, "gcp", gke_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_estimate_gke_cluster_golden_fixture(populated_combined_db: str) -> None:
    """Verify standard GKE cluster cost estimate matches the golden fixture exactly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "gke-golden",
                "service": "container",
                "kind": "gke_cluster",
                "region": "us-central1",
                "attributes": {
                    "machine_type": "e2-standard-4",
                    "node_count": 3,
                    "disk_size_gb": 100,
                    "disk_type": "pd-standard",
                },
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    with Path("tests/fixtures/gke_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_gke_cluster_no_nodes_management_fee_only(populated_combined_db: str) -> None:
    """Verify GKE cluster with no nodes has only management fee."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "gke-no-nodes",
                "service": "container",
                "kind": "gke_cluster",
                "region": "us-central1",
                "attributes": {
                    "node_count": 0,
                },
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    assert pytest.approx(est.monthly_total, abs=1e-4) == 73.00
    assert len(est.line_items) == 1
    assert est.line_items[0].component == "management_fee"


def test_estimate_gke_node_pool_standalone(populated_combined_db: str) -> None:
    """Verify standalone node pool only estimates compute and disk resources, no management fee."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "pool-standalone",
                "service": "container",
                "kind": "gke_node_pool",
                "region": "us-central1",
                "attributes": {
                    "machine_type": "e2-standard-4",
                    "node_count": 2,
                    "disk_size_gb": 50,
                    "disk_type": "pd-standard",
                },
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    # Math explanation:
    # CPU is 0.021811 times 8 vcpus times 730 hours
    # RAM is 0.002923 times 32 gib times 730 hours
    # Disk is 0.040 times 100 gb
    # Combined expected total is 199.65752
    assert pytest.approx(est.monthly_total, abs=1e-4) == 199.65752
    assert len(est.line_items) == 3
    assert not any(item.component == "management_fee" for item in est.line_items)


def test_estimate_gke_cluster_plus_separate_node_pool_combined_model(
    populated_combined_db: str,
) -> None:
    """Verify combined model of a cluster and separate node pool calculates correctly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "gke-cluster",
                "service": "container",
                "kind": "gke_cluster",
                "region": "us-central1",
                "attributes": {
                    "node_count": 0,  # cluster has no nodes, just flat fee
                },
            },
            {
                "provider": "gcp",
                "resource_id": "gke-pool",
                "service": "container",
                "kind": "gke_node_pool",
                "region": "us-central1",
                "attributes": {
                    "machine_type": "e2-standard-4",
                    "node_count": 2,
                    "disk_size_gb": 50,
                    "disk_type": "pd-standard",
                },
            },
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    # Costs:
    # Cluster Mgmt: $73.00
    # Pool Node Compute: $199.65752
    # Combined expected total = 73.00 + 199.65752 = 272.65752
    assert pytest.approx(est.monthly_total, abs=1e-4) == 272.65752
    assert len(est.line_items) == 4


def test_estimate_gke_combined_with_gce_instance(populated_combined_db: str) -> None:
    """Verify combined estimate of GKE cluster and GCE instance works correctly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "gke-cluster",
                "service": "container",
                "kind": "gke_cluster",
                "region": "us-central1",
                "attributes": {
                    "node_count": 0,  # cluster has no nodes, just flat fee
                },
            },
            {
                "provider": "gcp",
                "resource_id": "gce-vm",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {
                    "machine_type": "e2-standard-4",
                },
            },
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_combined_db, model)

    # Costs:
    # Cluster Mgmt: $73.00
    # GCE VM: vcpu (0.021811 * 4 * 730 = 63.68812) + ram (0.002923 * 16 * 730 = 34.14064) = 97.82876
    # Combined expected total = 73.00 + 97.82876 = 170.82876
    assert pytest.approx(est.monthly_total, abs=1e-4) == 170.82876
