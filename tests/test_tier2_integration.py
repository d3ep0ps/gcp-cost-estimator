# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.service import estimate_infrastructure
from gcp_cost_estimator.core.validate import validate_resource_model


@pytest.fixture
def populated_tier2_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with mock SKUs for Run, Functions, and App Engine."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load Run mock SKUs
    with Path("tests/fixtures/run_skus.json").open() as f:
        run_skus = json.load(f)

    # Load Functions mock SKUs
    with Path("tests/fixtures/function_skus.json").open() as f:
        fn_skus = json.load(f)

    # Load App Engine mock SKUs
    with Path("tests/fixtures/appengine_skus.json").open() as f:
        ae_skus = json.load(f)

    # Combine and de-duplicate (remove Metadata citations if any)
    all_skus = run_skus + fn_skus + ae_skus
    clean_skus = []
    seen_sku_ids = set()
    for s in all_skus:
        if s["sku_id"] != "METADATA-CITATION" and s["sku_id"] not in seen_sku_ids:
            clean_skus.append(s)
            seen_sku_ids.add(s["sku_id"])

    update_cache(temp_db_path, "gcp", clean_skus, "2026-06-08T12:00:00Z")
    return temp_db_path


@pytest.fixture
def tier2_combined_model() -> ResourceModel:
    """Create a ResourceModel featuring one of each Tier 2 resource with explicit usage."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "run-service",
                "service": "run",
                "kind": "cloud_run_service",
                "region": "us-central1",
                "attributes": {
                    "cpu": "2",
                    "memory": "4.0",
                    "cpu_idle": False,
                },
                "usage": {
                    "runtime_seconds_per_invocation": 1.0,
                    "invocations_per_month": 10000,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "run-job",
                "service": "run",
                "kind": "cloud_run_job",
                "region": "us-central1",
                "attributes": {
                    "cpu": "1",
                    "memory": "2.0",
                },
                "usage": {
                    "task_count": 5,
                    "runtime_seconds_per_task": 45,
                    "executions_per_month": 10,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "fn-1st",
                "service": "functions",
                "kind": "cloud_function",
                "region": "us-central1",
                "attributes": {
                    "available_memory_mb": 256,
                    "generation": "1st_gen",
                },
                "usage": {
                    "invocations_per_month": 1000000,
                    "avg_execution_time_ms": 100,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "fn-2nd",
                "service": "functions",
                "kind": "cloud_function",
                "region": "us-central1",
                "attributes": {
                    "available_cpu": "1",
                    "available_memory": "2.0Gi",
                    "generation": "2nd_gen",
                },
                "usage": {
                    "invocations_per_month": 10000,
                    "runtime_seconds_per_invocation": 2.0,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "ae-standard",
                "service": "appengine",
                "kind": "app_engine_standard_version",
                "region": "us-central1",
                "attributes": {
                    "instance_class": "F2",
                },
                "usage": {
                    "runtime_hours_per_month": 100,
                },
            },
            {
                "provider": "gcp",
                "resource_id": "ae-flexible",
                "service": "appengine",
                "kind": "app_engine_flexible_version",
                "region": "us-central1",
                "attributes": {
                    "cpu": 2,
                    "memory_gb": 4.0,
                    "disk_gb": 20,
                },
                "usage": {
                    "runtime_hours_per_month": 100,
                },
                "attached": [
                    {
                        "kind": "pd_persistent_disk",
                        "quantity": 1,
                        "attributes": {"size_gb": 20},
                    }
                ],
            },
        ]
    }
    return ResourceModel(**data)


def test_tier2_validate_returns_valid_for_combined_model(
    tier2_combined_model: ResourceModel,
) -> None:
    """Verify that the combined resource model validates without errors."""
    res = validate_resource_model(tier2_combined_model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_tier2_estimate_unpriced_list_empty_for_well_formed_model(
    populated_tier2_db: str, tier2_combined_model: ResourceModel
) -> None:
    """Verify that a fully specified Tier 2 model has no unpriced items."""
    est = estimate_infrastructure(populated_tier2_db, tier2_combined_model)
    assert len(est.unpriced) == 0


def test_tier2_estimate_all_services_present_in_line_items(
    populated_tier2_db: str, tier2_combined_model: ResourceModel
) -> None:
    """Verify that Run, Functions, and App Engine contribute correct subtotals to the final estimate."""
    est = estimate_infrastructure(populated_tier2_db, tier2_combined_model)

    # Check total cost: 115.636 (run-service) + 0.066 (run-job) + 0.8625 (fn-1) + 0.584 (fn-2) + 10.00 (ae-std) + 14.16 (ae-flex)
    # Total cost: 141.3085
    assert pytest.approx(est.monthly_total, abs=1e-4) == 141.3085

    # Verify that all resource_ids appear in the line items
    resource_ids = {item.resource_id for item in est.line_items}
    assert resource_ids == {
        "run-service",
        "run-job",
        "fn-1st",
        "fn-2nd",
        "ae-standard",
        "ae-flexible",
    }


def test_tier2_estimate_each_service_contributes_correct_subtotal(
    populated_tier2_db: str, tier2_combined_model: ResourceModel
) -> None:
    """Verify subtotals for each component resource are calculated correctly."""
    est = estimate_infrastructure(populated_tier2_db, tier2_combined_model)

    subtotals = {}
    for item in est.line_items:
        subtotals[item.resource_id] = subtotals.get(item.resource_id, 0.0) + item.monthly_cost

    assert pytest.approx(subtotals["run-service"], abs=1e-4) == 115.636
    assert pytest.approx(subtotals["run-job"], abs=1e-4) == 0.066
    assert pytest.approx(subtotals["fn-1st"], abs=1e-4) == 0.8625
    assert pytest.approx(subtotals["fn-2nd"], abs=1e-4) == 0.584
    assert pytest.approx(subtotals["ae-standard"], abs=1e-4) == 10.00
    assert pytest.approx(subtotals["ae-flexible"], abs=1e-4) == 14.16
