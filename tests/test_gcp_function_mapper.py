# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.pricing.gcp import GcpSkuMapper
from gcp_cost_estimator.core.service import estimate_infrastructure


@pytest.fixture
def populated_function_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Cloud Functions SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/function_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-08T12:00:00Z")
    return temp_db_path


def test_cloud_function_1stgen_invocation_sku_resolved_and_priced(
    populated_function_db: str,
) -> None:
    """Verify invocations SKU is resolved and priced for 1st-gen Cloud Functions."""
    r = Resource(
        provider="gcp",
        resource_id="fn-1",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
        usage={
            "invocations_per_month": 5000000,
            "avg_execution_time_ms": 200,
        },
    )
    mapper = GcpSkuMapper(populated_function_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)

    assert len(unpriced) == 0
    inv_map = next(m for m in mappings if m["component"] == "requests")
    assert inv_map["sku_id"] == "SKU-FN-INVOCATIONS"
    assert inv_map["qty"] == 5000000


def test_cloud_function_1stgen_compute_time_uses_tier1_or_tier2_rate_by_region(
    populated_function_db: str,
) -> None:
    """Verify compute time uses appropriate pricing tiers depending on the region (Tier 1 vs Tier 2)."""
    # Tier 1 Region
    r_t1 = Resource(
        provider="gcp",
        resource_id="fn-t1",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
        usage={
            "invocations_per_month": 1000000,
            "avg_execution_time_ms": 100,
        },
    )
    mapper = GcpSkuMapper(populated_function_db)
    mappings_t1, _ = mapper.map_resource_to_skus(r_t1)
    cpu_t1 = next(m for m in mappings_t1 if m["component"] == "vcpu")
    assert cpu_t1["sku_id"] == "SKU-FN-CPU-ACTIVE-T1"

    # Tier 2 Region
    r_t2 = Resource(
        provider="gcp",
        resource_id="fn-t2",
        service="functions",
        kind="cloud_function",
        region="europe-west4",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
        usage={
            "invocations_per_month": 1000000,
            "avg_execution_time_ms": 100,
        },
    )
    mappings_t2, _ = mapper.map_resource_to_skus(r_t2)
    cpu_t2 = next(m for m in mappings_t2 if m["component"] == "vcpu")
    assert cpu_t2["sku_id"] == "SKU-FN-CPU-ACTIVE-T2"


def test_cloud_function_1stgen_cost_equals_hand_computed_value_for_known_class(
    populated_function_db: str,
) -> None:
    """Verify cost calculation against hand-computed expected value."""
    # 256 MB function has 0.4 GHz CPU and 0.25 GB memory.
    # us-central1 (Tier 1) active prices: GB-sec = 0.0000025, GHz-sec = 0.0000100, inv = 0.00000040
    # Usage: 10,000,000 invocations of 200ms duration.
    # Hand-computed active duration: 10M * 0.2s = 2,000,000 seconds
    # Active GB-seconds = 2M * 0.25 GB = 500,000 GB-seconds
    # Active GHz-seconds = 2M * 0.4 GHz = 800,000 GHz-seconds
    # Memory cost = 500,000 * $0.0000025 = 1.25
    # CPU cost = 800,000 * $0.0000100 = 8.00
    # Invocations cost = 10,000,000 * $0.00000040 = 4.00
    # Total = 1.25 + 8.00 + 4.00 = 13.25
    r = Resource(
        provider="gcp",
        resource_id="fn-calc",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
        usage={
            "invocations_per_month": 10000000,
            "avg_execution_time_ms": 200,
        },
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_function_db, model)

    assert len(est.unpriced) == 0
    assert abs(est.monthly_total - 13.25) < 1e-4


def test_cloud_function_1stgen_idle_rate_applied_when_min_instances_set(
    populated_function_db: str,
) -> None:
    """Verify that idle rates and quantities are correctly computed for min_instances > 0."""
    # 256 MB (0.4 GHz / 0.25 GB) function with min_instances = 1
    # us-central1 (Tier 1)
    # Active execution: 1,000,000 invocations * 250ms = 250,000s duration.
    # Active GB-seconds: 250,000 * 0.25 = 62,500 GB-sec
    # Active GHz-seconds: 250,000 * 0.4 = 100,000 GHz-sec
    # Idle duration: max(0, 1 * 730 * 3600 - 250,000) = 2,628,000 - 250,000 = 2,378,000s
    # Idle GB-seconds: 2,378,000 * 0.25 = 594,500 GB-sec
    # Idle GHz-seconds: 2,378,000 * 0.4 = 951,200 GHz-sec
    # Costs:
    # Active GB-seconds: 62,500 * $0.0000025 = 0.15625
    # Idle GB-seconds: 594,500 * $0.0000025 = 1.48625
    # Active GHz-seconds: 100,000 * $0.0000100 = 1.00
    # Idle GHz-seconds: 951,200 * $0.000001042 = 0.9911504
    # Invocations: 1,000,000 * $0.00000040 = 0.40
    # Total = 0.15625 + 1.48625 + 1.00 + 0.9911504 + 0.40 = 4.0336504
    r = Resource(
        provider="gcp",
        resource_id="fn-idle",
        service="functions",
        kind="cloud_function",
        region="us-central1",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
            "min_instances": 1,
        },
        usage={
            "invocations_per_month": 1000000,
            "avg_execution_time_ms": 250,
        },
    )
    model = ResourceModel(resources=[r])
    est = estimate_infrastructure(populated_function_db, model)

    assert len(est.unpriced) == 0
    assert abs(est.monthly_total - 4.2128104) < 1e-4


def test_cloud_function_1stgen_unknown_region_surfaced_as_unpriced(
    populated_function_db: str,
) -> None:
    """Verify that mapping for unknown region flags the resource as unpriced."""
    r = Resource(
        provider="gcp",
        resource_id="fn-unknown",
        service="functions",
        kind="cloud_function",
        region="europe-north99",
        attributes={
            "available_memory_mb": 256,
            "generation": "1st_gen",
        },
    )
    mapper = GcpSkuMapper(populated_function_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)

    assert len(mappings) == 0
    assert len(unpriced) > 0
    assert any("no pricing data" in u["reason"].lower() for u in unpriced)
