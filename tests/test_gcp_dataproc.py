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


def test_dataproc_cluster_valid() -> None:
    """Verify dataproc cluster is valid."""
    r = Resource(
        provider="gcp",
        resource_id="dp-1",
        service="dataproc",
        kind="dataproc_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_dataproc_serverless_batch_unpriced() -> None:
    """Verify dataproc serverless batch is flagged as unpriced."""
    r = Resource(
        provider="gcp",
        resource_id="dp-2",
        service="dataproc",
        kind="dataproc_serverless_batch",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["unpriced"]) == 1
    assert "serverless" in res["unpriced"][0]["reason"].lower()


def test_dataproc_cluster_defaults_applied() -> None:
    """Verify default values are properly populated for Dataproc."""
    r = Resource(
        provider="gcp",
        resource_id="dp-1",
        service="dataproc",
        kind="dataproc_cluster",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage.get("runtime_hours_per_month") == 100
    assert norm_r.attributes.get("num_master_nodes") == 1
    assert norm_r.attributes.get("num_worker_nodes") == 2
    assert norm_r.attributes.get("num_preemptible_nodes") == 0
    assert norm_r.attributes.get("master_machine_type") == "n1-standard-4"
    assert norm_r.attributes.get("worker_machine_type") == "n1-standard-4"
    assert norm_r.usage.get("num_master_vcpus") == 4
    assert norm_r.usage.get("num_worker_vcpus") == 4
    assert any("runtime to 100 hours" in a for a in norm_r.assumptions)


@pytest.fixture
def populated_dataproc_db(temp_db_path: str) -> str:
    """Pre-populate temporary cache database with Dataproc & Compute SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/dataproc_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out metadata
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_dataproc_premium_fee_mapped(populated_dataproc_db: str) -> None:
    """Verify Dataproc Premium SKU matches and quantity is total vCPU * hours."""
    # (1 master * 4 vcpu + 2 workers * 4 vcpu) * 100 hours = 12 vcpu * 100 hours = 1200 hours
    r = Resource(
        provider="gcp",
        resource_id="dp-1",
        service="dataproc",
        kind="dataproc_cluster",
        region="us-central1",
        attributes={
            "num_master_nodes": 1,
            "num_worker_nodes": 2,
            "num_preemptible_nodes": 0,
            "master_machine_type": "n1-standard-4",
            "worker_machine_type": "n1-standard-4",
        },
        usage={
            "runtime_hours_per_month": 100,
            "num_master_vcpus": 4,
            "num_worker_vcpus": 4,
        },
    )
    mapper = GcpSkuMapper(populated_dataproc_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    premium = next(m for m in mappings if m["component"] == "dataproc_premium")
    assert premium["sku_id"] == "SKU-DATAPROC-PREMIUM"
    assert premium["qty"] == 1200.0
    assert premium["unit_price"] == 0.010


def test_dataproc_known_answer_estimate(populated_dataproc_db: str) -> None:
    """Verify known-answer calculation for Dataproc cluster (Premium + GCE VMs)."""
    # Total vCPUs: (1 * 4) + (2 * 4) = 12 vCPUs
    # Premium: 12 * 100 * 0.010 = $12.00
    # Master VM:
    #   CPU: 4 * 100 * 0.0475 = $19.00
    #   RAM: 15 GB (n1-standard-4 RAM is 15GB) * 100 * 0.0063 = $9.45
    # Workers VMs (2 workers):
    #   CPU: 8 * 100 * 0.0475 = $38.00
    #   RAM: 30 GB * 100 * 0.0063 = $18.90
    # Total = 12.00 + 19.00 + 9.45 + 38.00 + 18.90 = $97.35
    r = Resource(
        provider="gcp",
        resource_id="dp-1",
        service="dataproc",
        kind="dataproc_cluster",
        region="us-central1",
        attributes={
            "num_master_nodes": 1,
            "num_worker_nodes": 2,
            "num_preemptible_nodes": 0,
            "master_machine_type": "n1-standard-4",
            "worker_machine_type": "n1-standard-4",
        },
        usage={
            "runtime_hours_per_month": 100,
            "num_master_vcpus": 4,
            "num_worker_vcpus": 4,
        },
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_dataproc_db, model)
    assert len(est.unpriced) == 0
    assert pytest.approx(est.monthly_total, abs=1e-4) == 97.35


def test_terraform_hcl_parses_google_dataproc() -> None:
    """Verify HCL parser resolves Dataproc resources and attributes."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    # Verify cluster
    cluster = next(
        r for r in model.resources if r.resource_id == "google_dataproc_cluster.my_cluster"
    )
    assert cluster.provider == "gcp"
    assert cluster.service == "dataproc"
    assert cluster.kind == "dataproc_cluster"
    assert cluster.region == "us-central1"
    assert cluster.attributes.get("num_master_nodes") == 1
    assert cluster.attributes.get("master_machine_type") == "n1-standard-4"
    assert cluster.attributes.get("num_worker_nodes") == 2
    assert cluster.attributes.get("worker_machine_type") == "n1-standard-4"
    assert cluster.attributes.get("num_preemptible_nodes") == 0

    # Verify serverless batch
    batch = next(
        r for r in model.resources if r.resource_id == "google_dataproc_serverless_batch.my_batch"
    )
    assert batch.provider == "gcp"
    assert batch.service == "dataproc"
    assert batch.kind == "dataproc_serverless_batch"
    assert batch.region == "us-central1"


def test_terraform_plan_json_dataproc_parsed() -> None:
    """Verify plan JSON parser resolves Dataproc resources."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/dataproc_plan.json")

    # Verify cluster
    cluster = next(
        r for r in model.resources if r.resource_id == "google_dataproc_cluster.my_cluster"
    )
    assert cluster.provider == "gcp"
    assert cluster.service == "dataproc"
    assert cluster.kind == "dataproc_cluster"
    assert cluster.region == "us-central1"
    assert cluster.attributes.get("num_master_nodes") == 1
    assert cluster.attributes.get("master_machine_type") == "n1-standard-4"
    assert cluster.attributes.get("num_worker_nodes") == 2
    assert cluster.attributes.get("worker_machine_type") == "n1-standard-4"
    assert cluster.attributes.get("num_preemptible_nodes") == 0

    # Verify serverless batch
    batch = next(
        r for r in model.resources if r.resource_id == "google_dataproc_serverless_batch.my_batch"
    )
    assert batch.provider == "gcp"
    assert batch.service == "dataproc"
    assert batch.kind == "dataproc_serverless_batch"
    assert batch.region == "us-central1"
