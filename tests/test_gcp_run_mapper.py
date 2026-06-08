# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_run_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Cloud Run SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/run_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-08T12:00:00Z")
    return temp_db_path


def test_cloud_run_instance_based_cpu_and_memory_skus_resolved(populated_run_db: str) -> None:
    """Verify that instance-based service (always allocated) resolves CPU/Memory Allocation SKUs."""
    resource = Resource(
        provider="gcp",
        resource_id="service-always-on",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "2",
            "memory": "4.0",
            "cpu_idle": False,
        },
        usage={
            "runtime_seconds_per_invocation": 1.0,
            "invocations_per_month": 10000,
        }
    )
    mapper = GcpSkuMapper(populated_run_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # For instance-based service, CPU always allocated -> pay for CPU continuously
    # vCPU quantity: 2 vCPUs * 730 hours * 3600 seconds = 5256000 vCPU-seconds
    # RAM quantity: 4.0 GB * 730 hours * 3600 seconds = 10512000 GB-seconds
    # Requests quantity: 10000
    cpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert cpu_map["sku_id"] == "SKU-RUN-CPU-ALLOC"
    assert cpu_map["qty"] == 2 * 730 * 3600

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SKU-RUN-RAM-ALLOC"
    assert ram_map["qty"] == 4.0 * 730 * 3600

    req_map = next(m for m in mappings if m["component"] == "requests")
    assert req_map["sku_id"] == "SKU-RUN-REQUESTS"
    assert req_map["qty"] == 10000


def test_cloud_run_request_based_active_and_idle_skus_resolved_separately(populated_run_db: str) -> None:
    """Verify request-based service splits CPU/Memory into active and idle components if min_instances set."""
    resource = Resource(
        provider="gcp",
        resource_id="service-req-based",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "2.0",
            "cpu_idle": True,
            "min_instance_count": 1,
        },
        usage={
            "runtime_seconds_per_invocation": 2.5,
            "invocations_per_month": 100000,
        }
    )
    mapper = GcpSkuMapper(populated_run_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Active CPU time: 100,000 * 2.5 seconds * 1 vCPU = 250,000 vCPU-seconds
    # Idle CPU time: (1 instance * 730 * 3600) - 250,000 = 2,378,000 vCPU-seconds
    # Memory active: 100,000 * 2.5 * 2.0 = 500,000 GB-seconds
    # Memory idle: (1 instance * 2.0 * 730 * 3600) - 500,000 = 4,756,000 GB-seconds
    cpu_active_map = next(m for m in mappings if m["sku_id"] == "SKU-RUN-CPU-ACTIVE")
    assert cpu_active_map["qty"] == 250000

    cpu_idle_map = next(m for m in mappings if m["sku_id"] == "SKU-RUN-CPU-IDLE")
    assert cpu_idle_map["qty"] == 2378000

    ram_active_map = next(m for m in mappings if m["sku_id"] == "SKU-RUN-RAM-ACTIVE")
    assert ram_active_map["qty"] == 500000

    ram_idle_map = next(m for m in mappings if m["sku_id"] == "SKU-RUN-RAM-IDLE")
    assert ram_idle_map["qty"] == 4756000


def test_cloud_run_job_uses_instance_based_skus_with_one_minute_minimum(populated_run_db: str) -> None:
    """Verify that jobs use allocation SKUs with a 1-minute minimum execution time per task."""
    resource = Resource(
        provider="gcp",
        resource_id="job-1",
        service="run",
        kind="cloud_run_job",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "2.0",
        },
        usage={
            "task_count": 5,
            "runtime_seconds_per_task": 45,  # Billed as 60s minimum!
            "executions_per_month": 10,
        }
    )
    mapper = GcpSkuMapper(populated_run_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Total billed seconds per task = max(45, 60) = 60s
    # Total vCPU seconds: 5 tasks * 60s * 10 executions * 1 vCPU = 3000 vCPU-seconds
    # Total Memory seconds: 5 tasks * 60s * 10 executions * 2.0 GB = 6000 GB-seconds
    cpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert cpu_map["sku_id"] == "SKU-RUN-CPU-ALLOC"
    assert cpu_map["qty"] == 3000

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SKU-RUN-RAM-ALLOC"
    assert ram_map["qty"] == 6000


def test_cloud_run_gpu_sku_resolved_when_gpu_type_present(populated_run_db: str) -> None:
    """Verify that Cloud Run GPU resolves properly when gpu_type and gpu_count are present."""
    resource = Resource(
        provider="gcp",
        resource_id="gpu-service",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "4",
            "memory": "16.0",
            "cpu_idle": False,
            "gpu_type": "nvidia-l4",
            "gpu_count": 1,
        },
        usage={
            "runtime_seconds_per_invocation": 10.0,
            "invocations_per_month": 1000,
        }
    )
    mapper = GcpSkuMapper(populated_run_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # GPU quantity for instance-based billing is billed continuously:
    # 1 GPU * 730 hours * 3600 seconds = 2628000 seconds
    gpu_map = next(m for m in mappings if m["component"] == "gpu")
    assert gpu_map["sku_id"] == "SKU-RUN-GPU"
    assert gpu_map["qty"] == 730 * 3600


def test_cloud_run_region_outside_known_tier_list_surfaced_as_unpriced(populated_run_db: str) -> None:
    """Verify that an unknown region surfaces the resource as unpriced."""
    resource = Resource(
        provider="gcp",
        resource_id="service-unknown-region",
        service="run",
        kind="cloud_run_service",
        region="europe-north99",
        attributes={
            "cpu": "1",
            "memory": "512Mi",
        }
    )
    mapper = GcpSkuMapper(populated_run_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) > 0
    assert any("no pricing data" in u["reason"].lower() or "no matching" in u["reason"].lower() for u in unpriced)
