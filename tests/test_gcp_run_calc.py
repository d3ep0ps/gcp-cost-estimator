# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.service import estimate_infrastructure


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


def test_cloud_run_instance_based_service_cost_equals_hand_computed_value(populated_run_db: str) -> None:
    """Verify that instance-based service cost equals hand-computed monthly value."""
    resource = Resource(
        provider="gcp",
        resource_id="service-always-on",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "2",
            "memory": "4.0",
            "cpu_idle": "false",
        },
        usage={
            "runtime_seconds_per_invocation": "1.0",
            "invocations_per_month": "10000",
        }
    )
    model = ResourceModel(resources=[resource])
    est = estimate_infrastructure(populated_run_db, model)

    assert len(est.unpriced) == 0
    # Expected hand-computed costs:
    # CPU: 2 vCPUs * 730h * 3600s * $0.000018 = 94.608
    # RAM: 4.0 GiB * 730h * 3600s * $0.000002 = 21.024
    # Requests: 10000 * $0.00000040 = 0.004
    # Total = 115.636
    assert abs(est.monthly_total - 115.636) < 1e-4

    # Verify line items
    cpu_item = next(item for item in est.line_items if item.component == "vcpu")
    assert cpu_item.sku_id == "SKU-RUN-CPU-ALLOC"
    assert abs(cpu_item.monthly_cost - 94.608) < 1e-4

    ram_item = next(item for item in est.line_items if item.component == "ram")
    assert ram_item.sku_id == "SKU-RUN-RAM-ALLOC"
    assert abs(ram_item.monthly_cost - 21.024) < 1e-4

    req_item = next(item for item in est.line_items if item.component == "requests")
    assert req_item.sku_id == "SKU-RUN-REQUESTS"
    assert abs(req_item.monthly_cost - 0.004) < 1e-4


def test_cloud_run_request_based_service_cost_splits_active_and_idle_correctly(populated_run_db: str) -> None:
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
            "cpu_idle": "true",
            "min_instance_count": "1",
        },
        usage={
            "runtime_seconds_per_invocation": "2.5",
            "invocations_per_month": "100000",
        }
    )
    model = ResourceModel(resources=[resource])
    est = estimate_infrastructure(populated_run_db, model)

    assert len(est.unpriced) == 0
    # Expected hand-computed costs:
    # Active CPU: 1 * 250,000s * $0.000024 = 6.00
    # Idle CPU: 1 * (2,628,000s - 250,000s) * $0.0000025 = 5.945
    # Active RAM: 2.0 * 250,000s * $0.0000025 = 1.25
    # Idle RAM: 2.0 * (2,628,000s - 250,000s) * $0.00000026 = 1.23656
    # Requests: 100,000 * $0.00000040 = 0.04
    # Total = 6.00 + 5.945 + 1.25 + 1.23656 + 0.04 = 14.47156
    assert abs(est.monthly_total - 14.47156) < 1e-4


def test_cloud_run_job_cost_applies_one_minute_minimum_per_task_instance(populated_run_db: str) -> None:
    """Verify jobs use allocation SKUs with a 1-minute minimum execution time per task."""
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
            "task_count": "5",
            "runtime_seconds_per_task": "45",  # Billed as 60s
            "executions_per_month": "10",
        }
    )
    model = ResourceModel(resources=[resource])
    est = estimate_infrastructure(populated_run_db, model)

    assert len(est.unpriced) == 0
    # Expected hand-computed costs:
    # Total seconds = max(45, 60) * 5 * 10 = 3000s
    # CPU: 1 * 3000s * $0.000018 = 0.054
    # RAM: 2.0 * 3000s * $0.000002 = 0.012
    # Total = 0.066
    assert abs(est.monthly_total - 0.066) < 1e-4


def test_cloud_run_gpu_cost_added_as_separate_line_item(populated_run_db: str) -> None:
    """Verify GPU cost added as a separate line item."""
    resource = Resource(
        provider="gcp",
        resource_id="gpu-service",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "4",
            "memory": "16.0",
            "cpu_idle": "false",
            "gpu_type": "nvidia-l4",
            "gpu_count": "1",
        },
        usage={
            "runtime_seconds_per_invocation": "10.0",
            "invocations_per_month": "1000",
        }
    )
    model = ResourceModel(resources=[resource])
    est = estimate_infrastructure(populated_run_db, model)

    assert len(est.unpriced) == 0
    # GPU cost: 1 GPU * 730h * 3600s * $0.000350 = 919.80
    gpu_item = next(item for item in est.line_items if item.component == "gpu")
    assert gpu_item.sku_id == "SKU-RUN-GPU"
    assert abs(gpu_item.monthly_cost - 919.80) < 1e-4


def test_cloud_run_estimate_includes_assumptions_for_invocation_volume(populated_run_db: str) -> None:
    """Verify that Cloud Run estimates document default invocation assumptions when usage is omitted."""
    resource = Resource(
        provider="gcp",
        resource_id="service-no-usage",
        service="run",
        kind="cloud_run_service",
        region="us-central1",
        attributes={
            "cpu": "1",
            "memory": "2.0",
        }
    )
    model = ResourceModel(resources=[resource])
    est = estimate_infrastructure(populated_run_db, model)

    # Validate normalizer defaults
    assert len(est.unpriced) == 0
    assert len(est.assumptions) > 0
    assert any("defaulted invocations_per_month" in a.lower() for a in est.assumptions)
