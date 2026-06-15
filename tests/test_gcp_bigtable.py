# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.service import estimate_infrastructure
from gcp_cost_estimator.core.validate import validate_resource_model


@pytest.fixture
def populated_bigtable_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Bigtable SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/bigtable_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    # GCE mock SKUs for combined tests
    gce_skus = [
        {
            "sku_id": "SKU-N2-CPU",
            "provider": "gcp",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core",
        },
        {
            "sku_id": "SKU-N2-RAM",
            "provider": "gcp",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram",
        },
    ]

    update_cache(temp_db_path, "gcp", mock_skus + gce_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


# ==========================================
# BT-1: Validation Tests
# ==========================================


def test_bigtable_instance_valid_production_single_cluster() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-1",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                    "clusters": [
                        {
                            "cluster_id": "cluster-1",
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                            "storage_type": "SSD",
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_bigtable_instance_valid_production_multi_cluster() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-2",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                    "clusters": [
                        {
                            "cluster_id": "cluster-1",
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                            "storage_type": "SSD",
                        },
                        {
                            "cluster_id": "cluster-2",
                            "zone": "europe-west1-b",
                            "num_nodes": 4,
                            "storage_type": "SSD",
                        },
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_bigtable_instance_valid_development() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-3",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "DEVELOPMENT",
                    "clusters": [
                        {
                            "cluster_id": "cluster-1",
                            "zone": "us-central1-a",
                            "num_nodes": 1,
                            "storage_type": "SSD",
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_bigtable_instance_development_num_nodes_not_1_flagged_as_error() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-4",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "DEVELOPMENT",
                    "clusters": [
                        {
                            "cluster_id": "cluster-1",
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("num_nodes is not 1" in e for e in result["errors"])


def test_bigtable_instance_production_fewer_than_3_nodes_flagged_as_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-5",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                    "clusters": [
                        {
                            "cluster_id": "cluster-1",
                            "zone": "us-central1-a",
                            "num_nodes": 2,
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("fewer than 3 nodes" in w for w in result["warnings"])


def test_bigtable_instance_missing_clusters_flagged_as_error() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-6",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("missing cluster configuration" in e for e in result["errors"])


def test_bigtable_instance_zone_converted_to_region() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-7",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "clusters": [
                        {
                            "zone": "us-east1-b",
                            "num_nodes": 3,
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].attributes["clusters"][0]["region"] == "us-east1"


def test_bigtable_instance_storage_type_defaults_to_ssd() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-8",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "clusters": [
                        {
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].attributes["clusters"][0]["storage_type"] == "SSD"
    assert any("Defaulted storage_type to SSD" in a for a in normalized.resources[0].assumptions)


def test_bigtable_instance_storage_defaults_to_zero_with_assumption() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-9",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "clusters": [
                        {
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].usage["storage_gb_per_cluster"] == 0
    assert any(
        "Defaulted storage_gb_per_cluster to 0" in a for a in normalized.resources[0].assumptions
    )


def test_bigtable_instance_runtime_defaults_to_730h() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-10",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "clusters": [
                        {
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                        }
                    ],
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized.resources[0].usage["runtime_hours_per_month"] == 730


# ==========================================
# BT-2: SKU Mapping Tests
# ==========================================


def test_bigtable_production_ssd_maps_to_node_sku(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-ssd",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 3,
                    "storage_type": "SSD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 0},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-BIGTABLE-SSD-NODE"
    assert mappings[0]["qty"] == 3 * 730


def test_bigtable_production_hdd_maps_to_hdd_node_sku(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-hdd",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 3,
                    "storage_type": "HDD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 0},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-BIGTABLE-HDD-NODE"


def test_bigtable_node_qty_is_num_nodes_times_runtime_hours(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-qty",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 5,
                    "storage_type": "SSD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 100, "storage_gb_per_cluster": 0},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert mappings[0]["qty"] == 5 * 100


def test_bigtable_storage_ssd_sku_emitted_when_nonzero(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-stor-ssd",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 3,
                    "storage_type": "SSD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 500},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 2
    stor = next(m for m in mappings if m["component"] == "storage")
    assert stor["sku_id"] == "SKU-BIGTABLE-SSD-STORAGE"
    assert stor["qty"] == 500.0


def test_bigtable_storage_hdd_sku_emitted_when_nonzero(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-stor-hdd",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 3,
                    "storage_type": "HDD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 1000},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 2
    stor = next(m for m in mappings if m["component"] == "storage")
    assert stor["sku_id"] == "SKU-BIGTABLE-HDD-STORAGE"
    assert stor["qty"] == 1000.0


def test_bigtable_storage_not_emitted_when_zero(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-no-stor",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 3,
                    "storage_type": "SSD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 0},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert not any(m["component"] == "storage" for m in mappings)


def test_bigtable_multi_cluster_each_cluster_has_own_skus(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-multi",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 3,
                    "storage_type": "SSD",
                },
                {
                    "region": "us-central1",
                    "zone": "us-central1-b",
                    "num_nodes": 4,
                    "storage_type": "SSD",
                },
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 100},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(unpriced) == 0
    # Two clusters: Node SKU for cluster 1 (qty 3*730=2190) + Node SKU for cluster 2 (qty 4*730=2920)
    # Plus two storage SKUs (each cluster gets 100GB storage billed since storage replicates)
    assert len(mappings) == 4
    nodes = [m for m in mappings if m["component"] == "compute"]
    assert sum(n["qty"] for n in nodes) == (3 + 4) * 730
    stors = [m for m in mappings if m["component"] == "storage"]
    assert sum(s["qty"] for s in stors) == 200.0


def test_bigtable_development_instance_1_node_mapped(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-dev",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "DEVELOPMENT",
            "clusters": [
                {
                    "region": "us-central1",
                    "zone": "us-central1-a",
                    "num_nodes": 1,
                    "storage_type": "SSD",
                }
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 0},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, _unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["qty"] == 1 * 730


def test_bigtable_unresolvable_region_reported_unpriced(populated_bigtable_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="bigtable-unres",
        service="bigtable",
        kind="bigtable_instance",
        region="us-central1",
        attributes={
            "instance_type": "PRODUCTION",
            "clusters": [
                {"region": None, "zone": "us-invalid-zone", "num_nodes": 3, "storage_type": "SSD"}
            ],
        },
        usage={"runtime_hours_per_month": 730, "storage_gb_per_cluster": 0},
    )
    mapper = GcpSkuMapper(populated_bigtable_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 0
    assert len(unpriced) > 0


# ==========================================
# BT-3: Cost Calculation Tests
# ==========================================


def test_bigtable_cost_cases(populated_bigtable_db: str) -> None:
    with Path("tests/fixtures/bigtable_cost_cases.json").open() as f:
        cases = json.load(f)

    for case in cases:
        res = Resource(
            provider="gcp",
            resource_id="bigtable-test",
            service="bigtable",
            kind="bigtable_instance",
            region=case["region"],
            attributes={
                "instance_type": case["instance_type"],
                "clusters": case["clusters"],
            },
            usage={
                "runtime_hours_per_month": case["runtime_hours"],
                "storage_gb_per_cluster": case["storage_gb_per_cluster"],
            },
        )
        model = ResourceModel(resources=[res])
        est = estimate_infrastructure(populated_bigtable_db, model)

        assert len(est.unpriced) == 0
        assert pytest.approx(est.monthly_total, abs=1e-4) == case["expected_total"]


# ==========================================
# BT-4: End-to-End Estimation Tests
# ==========================================


def test_estimate_bigtable_production_ssd_golden_fixture(populated_bigtable_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bigtable-golden",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                    "clusters": [
                        {
                            "cluster_id": "us-central1-cluster",
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                            "storage_type": "SSD",
                        }
                    ],
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                    "storage_gb_per_cluster": 100.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_bigtable_db, model)

    with Path("tests/fixtures/bigtable_estimate_golden.json").open() as f:
        golden = json.load(f)

    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert pytest.approx(est.monthly_total, abs=1e-4) == golden["monthly_total"]
    assert len(est.unpriced) == len(golden["unpriced"])
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        golden_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert golden_item["sku_id"] == item.sku_id
        assert pytest.approx(golden_item["monthly_cost"], abs=1e-4) == item.monthly_cost


def test_estimate_bigtable_combined_with_gce_instance(populated_bigtable_db: str) -> None:
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
            },
            {
                "provider": "gcp",
                "resource_id": "bigtable-golden",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "instance_type": "PRODUCTION",
                    "clusters": [
                        {
                            "cluster_id": "us-central1-cluster",
                            "zone": "us-central1-a",
                            "num_nodes": 3,
                            "storage_type": "SSD",
                        }
                    ],
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                    "storage_gb_per_cluster": 100.0,
                },
            },
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_bigtable_db, model)
    # GCE CPU is 0.0475 * 4 * 730 = 138.7. GCE RAM is 0.0063 * 16 = 0.1008. Total GCE is 138.8008
    # Bigtable cost is 1440.50
    # The expected total cost is 1579.3008
    assert pytest.approx(est.monthly_total, abs=1e-4) == 1579.3008
    assert len(est.line_items) == 4


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_bigtable_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "bt-1",
                "service": "bigtable",
                "kind": "bigtable_instance",
                "region": "us-central1",
                "attributes": {
                    "clusters": [
                        {
                            "zone": "us-central1-a",
                        }
                    ]
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_bigtable_db, model)
    assert est.disclaimer != ""
    assert "list price only" in est.disclaimer.lower()
    assert est.pricing_snapshot == "2026-06-10T12:00:00Z"
