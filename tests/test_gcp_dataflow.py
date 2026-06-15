# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path
import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.service import estimate_infrastructure


def test_dataflow_job_valid_batch() -> None:
    """Verify batch dataflow job is valid."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "batch"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_dataflow_job_valid_streaming() -> None:
    """Verify streaming dataflow job is valid."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "streaming"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_dataflow_job_type_default_is_batch() -> None:
    """Verify default job_type is batch."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage.get("job_type") == "batch"
    assert any("job_type" in a for a in norm_r.assumptions)


def test_dataflow_machine_type_resolved_via_specs() -> None:
    """Verify vcpu and ram are resolved from machine_type."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        attributes={"machine_type": "n1-standard-8"},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage.get("num_vcpus") == 8
    assert norm_r.usage.get("memory_gb") == 30.0


def test_dataflow_max_workers_default_applied() -> None:
    """Verify max_workers defaults to 1."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes.get("max_workers") == 1
    assert any("max_workers" in a for a in norm_r.assumptions)


def test_dataflow_unknown_region_flagged_as_unpriced() -> None:
    """Verify unknown region flags the resource as unpriced."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="unknown-region",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["unpriced"]) == 1
    assert "region" in res["unpriced"][0]["reason"].lower()


def test_dataflow_runtime_default_applied_with_assumption() -> None:
    """Verify runtime_hours_per_month defaults to 100."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage.get("runtime_hours_per_month") == 100
    assert any("100 hours" in a for a in norm_r.assumptions)


@pytest.fixture
def populated_dataflow_db(temp_db_path: str) -> str:
    """Pre-populate temporary cache database with Dataflow SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/dataflow_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out metadata
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_dataflow_batch_vcpu_priced(populated_dataflow_db: str) -> None:
    """Verify batch vCPU is priced correctly."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        attributes={"max_workers": 2},
        usage={"job_type": "batch", "num_vcpus": 4, "runtime_hours_per_month": 100},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "vcpu")
    assert item["sku_id"] == "SKU-DF-BATCH-CPU"
    assert item["qty"] == 4 * 100 * 2
    assert item["unit_price"] == 0.056


def test_dataflow_batch_memory_priced(populated_dataflow_db: str) -> None:
    """Verify batch memory is priced correctly."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        attributes={"max_workers": 2},
        usage={"job_type": "batch", "memory_gb": 15, "runtime_hours_per_month": 100},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "ram")
    assert item["sku_id"] == "SKU-DF-BATCH-RAM"
    assert item["qty"] == 15 * 100 * 2
    assert item["unit_price"] == 0.003557


def test_dataflow_batch_shuffle_priced_with_volume_adjustment(populated_dataflow_db: str) -> None:
    """Verify batch Shuffle pricing has tiered reduction applied."""
    # 50 GB Shuffle: 50 * 0.25 (75% reduction) = 12.5 GB billable
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "batch", "shuffle_data_gb": 50},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "shuffle")
    assert item["sku_id"] == "SKU-DF-SHUFFLE"
    assert item["qty"] == 12.5
    assert item["unit_price"] == 0.011


def test_dataflow_streaming_vcpu_priced_at_higher_rate(populated_dataflow_db: str) -> None:
    """Verify streaming vCPU is priced at streaming rate."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "streaming", "num_vcpus": 4, "runtime_hours_per_month": 100},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "vcpu")
    assert item["sku_id"] == "SKU-DF-STREAMING-CPU"
    assert item["unit_price"] == 0.069


def test_dataflow_streaming_engine_units_priced(populated_dataflow_db: str) -> None:
    """Verify streaming engine compute units are mapped and priced."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "streaming", "num_vcpus": 8, "runtime_hours_per_month": 100},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "streaming_engine")
    assert item["sku_id"] == "SKU-DF-STREAMING-ENGINE"
    # 8 vcpus -> 8 / 4 = 2.0 Streaming Engine units
    assert item["qty"] == 2.0 * 100
    assert item["unit_price"] == 0.089


def test_dataflow_pd_storage_priced(populated_dataflow_db: str) -> None:
    """Verify workers' PD standard storage is priced."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        attributes={"max_workers": 2, "disk_size_gb": 250},
        usage={"runtime_hours_per_month": 100},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "storage")
    assert item["sku_id"] == "SKU-DF-STORAGE"
    assert item["qty"] == 250 * 2 * 100
    assert item["unit_price"] == 0.000054


def test_dataflow_known_answer_batch_4vcpu_15gb_100h_50gb_shuffle(populated_dataflow_db: str) -> None:
    """Verify known-answer calculation for a batch Dataflow job."""
    # CPU: 4 vCPU * 100 hrs * 1 worker = 400 hrs * 0.056 = $22.40
    # Memory: 15 GB * 100 hrs * 1 worker = 1500 hrs * 0.003557 = $5.3355
    # Shuffle: 50 GB -> 12.5 billable GB * 0.011 = $0.1375
    # Storage: 250 GB * 1 worker * 100 hrs = 25000 GB-hrs * 0.000054 = $1.35
    # Total = 22.40 + 5.3355 + 0.1375 + 1.35 = $29.223
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        attributes={"max_workers": 1, "disk_size_gb": 250},
        usage={"job_type": "batch", "num_vcpus": 4, "memory_gb": 15, "runtime_hours_per_month": 100, "shuffle_data_gb": 50},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total = sum(m["qty"] * m["unit_price"] for m in mappings)
    assert pytest.approx(total, abs=1e-4) == 29.223


def test_dataflow_known_answer_streaming_4vcpu_15gb_730h(populated_dataflow_db: str) -> None:
    """Verify known-answer calculation for a streaming Dataflow job."""
    # CPU: 4 vCPU * 730 hrs * 1 worker = 2920 hrs * 0.069 = $201.48
    # Memory: 15 GB * 730 hrs * 1 worker = 10950 hrs * 0.003557 = $38.94915
    # Streaming Engine Units: 4 vcpus -> 1 unit * 730 hrs = 730 hrs * 0.089 = $64.97
    # Storage: 250 GB * 1 worker * 730 hrs = 182500 GB-hrs * 0.000054 = $9.855
    # Total = 201.48 + 38.94915 + 64.97 + 9.855 = $315.25415
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        attributes={"max_workers": 1, "disk_size_gb": 250},
        usage={"job_type": "streaming", "num_vcpus": 4, "memory_gb": 15, "runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_dataflow_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total = sum(m["qty"] * m["unit_price"] for m in mappings)
    assert pytest.approx(total, abs=1e-4) == 315.25415


def test_terraform_hcl_parses_google_dataflow_job() -> None:
    """Verify HCL parser resolves google_dataflow_job resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_dataflow_job.my_job")
    assert res.provider == "gcp"
    assert res.service == "dataflow"
    assert res.kind == "dataflow_job"
    assert res.region == "us-central1"


def test_terraform_hcl_max_workers_extracted() -> None:
    """Verify HCL parser extracts max_workers parameter."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_dataflow_job.my_job")
    assert res.attributes.get("max_workers") == 2


def test_terraform_hcl_machine_type_extracted() -> None:
    """Verify HCL parser extracts machine_type parameter."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_dataflow_job.my_job")
    assert res.attributes.get("machine_type") == "n1-standard-4"


def test_terraform_plan_json_dataflow_job_parsed() -> None:
    """Verify plan JSON parser resolves dataflow_job resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/dataflow_plan.json")
    res = next(r for r in model.resources if r.resource_id == "google_dataflow_job.my_job")
    assert res.provider == "gcp"
    assert res.service == "dataflow"
    assert res.kind == "dataflow_job"
    assert res.region == "us-central1"
    assert res.attributes.get("max_workers") == 2
    assert res.attributes.get("machine_type") == "n1-standard-4"


def test_dataflow_estimate_includes_disclaimer(populated_dataflow_db: str) -> None:
    """Verify Dataflow estimate includes standard list price disclaimer."""
    r = Resource(
        provider="gcp",
        resource_id="df-1",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_dataflow_db, model)
    assert est.disclaimer != ""


def test_dataflow_batch_and_streaming_separate_line_items(populated_dataflow_db: str) -> None:
    """Verify batch and streaming jobs produce separate line items."""
    b = Resource(
        provider="gcp",
        resource_id="batch-job",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "batch"},
    )
    s = Resource(
        provider="gcp",
        resource_id="stream-job",
        service="dataflow",
        kind="dataflow_job",
        region="us-central1",
        usage={"job_type": "streaming"},
    )
    model = ResourceModel(resources=[b, s])
    est = estimate_infrastructure(populated_dataflow_db, model)
    # Total line items: batch CPU, batch RAM, batch Storage, batch Shuffle, streaming CPU, streaming RAM, streaming Storage, streaming Engine
    assert len(est.line_items) == 8
    # Assert they are separate resources
    assert any(item.resource_id == "batch-job" for item in est.line_items)
    assert any(item.resource_id == "stream-job" for item in est.line_items)


def test_dataflow_unpriced_region_in_unpriced_list(populated_dataflow_db: str) -> None:
    """Verify jobs running in unpriced regions land in the unpriced list of the estimate."""
    r = Resource(
        provider="gcp",
        resource_id="unpriced-job",
        service="dataflow",
        kind="dataflow_job",
        region="invalid-region",
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_dataflow_db, model)
    assert len(est.unpriced) == 1
    assert est.unpriced[0].resource_id == "unpriced-job"
    assert "region" in est.unpriced[0].reason.lower()
