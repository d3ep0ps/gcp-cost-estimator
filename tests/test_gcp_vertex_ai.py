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
def populated_vertex_ai_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Vertex AI SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/vertex_ai_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-15T12:00:00Z")
    return temp_db_path


# ==========================================
# Validation & Normalisation Tests
# ==========================================


def test_validate_vertex_ai_endpoint_shared_adds_unpriced() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "endpoint-shared",
                "service": "vertex",
                "kind": "google_vertex_ai_endpoint",
                "region": "us-central1",
                "attributes": {
                    "dedicated_endpoint_enabled": False,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    # Should warn that inference is unpriced, and that it is shared
    assert len(result["unpriced"]) > 0
    assert any("shared endpoint" in item["reason"] for item in result["unpriced"])


def test_validate_vertex_ai_endpoint_dedicated_is_valid() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "endpoint-dedicated",
                "service": "vertex",
                "kind": "google_vertex_ai_endpoint",
                "region": "us-central1",
                "attributes": {
                    "dedicated_endpoint_enabled": True,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["unpriced"]) == 0


def test_validate_vertex_ai_endpoint_normalises_location() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "endpoint-norm",
                "service": "vertex",
                "kind": "google_vertex_ai_endpoint",
                "region": "us-central1",
                "attributes": {
                    "location": "US-CENTRAL1",
                    "dedicated_endpoint_enabled": True,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["location"] == "us-central1"


# ==========================================
# SKU Mapping & Cost Calculation Tests
# ==========================================


def test_vertex_ai_dedicated_endpoint_cost(populated_vertex_ai_db: str) -> None:
    # Default n1-standard-2: 1 node * $0.1095 * 730 hr = $79.935
    res = Resource(
        provider="gcp",
        resource_id="my-endpoint",
        service="vertex",
        kind="google_vertex_ai_endpoint",
        region="us-central1",
        attributes={"dedicated_endpoint_enabled": True},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vertex_ai_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-VERTEXAI-PREDICTION-N1-STANDARD-2"
    assert mappings[0]["qty"] == 1 * 730
    assert any("inference traffic costs" in u["reason"] for u in unpriced)


def test_vertex_ai_dedicated_n1_standard_4_cost(populated_vertex_ai_db: str) -> None:
    # n1-standard-4: 1 node * $0.2190 * 730 hr = $159.87
    res = Resource(
        provider="gcp",
        resource_id="my-endpoint-large",
        service="vertex",
        kind="google_vertex_ai_endpoint",
        region="us-central1",
        attributes={
            "dedicated_endpoint_enabled": True,
            "machine_type": "n1-standard-4",
        },
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vertex_ai_db)
    mappings, _ = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-VERTEXAI-PREDICTION-N1-STANDARD-4"
    assert mappings[0]["qty"] == 1 * 730


def test_vertex_ai_shared_endpoint_zero_cost_all_unpriced(populated_vertex_ai_db: str) -> None:
    res = Resource(
        provider="gcp",
        resource_id="shared-endpoint",
        service="vertex",
        kind="google_vertex_ai_endpoint",
        region="us-central1",
        attributes={"dedicated_endpoint_enabled": False},
        usage={"runtime_hours_per_month": 730},
    )
    mapper = GcpSkuMapper(populated_vertex_ai_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 0
    assert len(unpriced) == 2
    assert any("shared endpoint" in u["reason"] for u in unpriced)


def test_estimate_vertex_ai_dedicated_e2e(populated_vertex_ai_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "endpoint-e2e",
                "service": "vertex",
                "kind": "google_vertex_ai_endpoint",
                "region": "us-central1",
                "attributes": {
                    "dedicated_endpoint_enabled": True,
                },
                "usage": {
                    "runtime_hours_per_month": 730,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_vertex_ai_db, model)
    assert est.monthly_total == pytest.approx(79.935, abs=1e-3)
    assert len(est.line_items) == 1
    assert est.line_items[0].component == "compute"
    assert len(est.unpriced) == 1
