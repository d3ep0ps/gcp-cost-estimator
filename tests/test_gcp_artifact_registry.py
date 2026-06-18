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
def populated_artifact_registry_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Artifact Registry SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/artifact_registry_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-15T12:00:00Z")
    return temp_db_path


# ==========================================
# Validation & Normalisation Tests
# ==========================================


def test_validate_artifact_registry_unknown_format_warns() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "repo-warn",
                "service": "artifact_registry",
                "kind": "artifact_registry_repository",
                "region": "us-central1",
                "attributes": {
                    "format": "UNKNOWN",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("unknown Artifact Registry format" in w for w in result["warnings"])
    # Validation must not append to unpriced to avoid skipping SKU mapping!
    assert len(result["unpriced"]) == 0


def test_validate_artifact_registry_normalises_format_and_location() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "repo-norm",
                "service": "artifact_registry",
                "kind": "artifact_registry_repository",
                "region": "us-central1",
                "attributes": {
                    "format": "docker",
                    "location": "US-CENTRAL1",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["format"] == "DOCKER"
    assert normalized.resources[0].attributes["location"] == "us-central1"


# ==========================================
# SKU Mapping & Cost Calculation Tests
# ==========================================


def test_artifact_registry_10gb_storage_cost(populated_artifact_registry_db: str) -> None:
    # 10 GB: (10.0 - 0.5) GB * $0.10/GB-month = $0.95
    res = Resource(
        provider="gcp",
        resource_id="repo-10gb",
        service="artifact_registry",
        kind="artifact_registry_repository",
        region="us-central1",
        attributes={"storage_gb": 10.0},
    )
    mapper = GcpSkuMapper(populated_artifact_registry_db)
    mappings, unpriced = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["sku_id"] == "SKU-ARTIFACT-REGISTRY-STORAGE"
    assert mappings[0]["qty"] == 9.5
    assert mappings[0]["unit_price"] == 0.10
    assert any("vulnerability scanning" in u["reason"] for u in unpriced)


def test_artifact_registry_below_free_tier_zero_cost(populated_artifact_registry_db: str) -> None:
    # 0.3 GB < 0.5 GB free -> $0.00
    res = Resource(
        provider="gcp",
        resource_id="repo-free",
        service="artifact_registry",
        kind="artifact_registry_repository",
        region="us-central1",
        attributes={"storage_gb": 0.3},
    )
    mapper = GcpSkuMapper(populated_artifact_registry_db)
    mappings, _ = mapper.map_resource_to_skus(res)
    assert len(mappings) == 1
    assert mappings[0]["qty"] == 0.0


def test_artifact_registry_egress_included_in_cost(populated_artifact_registry_db: str) -> None:
    # 10 GB storage + 50 GB egress = $0.95 storage + $0.50 egress = $1.45
    res = Resource(
        provider="gcp",
        resource_id="repo-egress",
        service="artifact_registry",
        kind="artifact_registry_repository",
        region="us-central1",
        attributes={
            "storage_gb": 10.0,
            "monthly_egress_gb": 50.0,
        },
    )
    mapper = GcpSkuMapper(populated_artifact_registry_db)
    mappings, _ = mapper.map_resource_to_skus(res)
    assert len(mappings) == 2

    storage = next(m for m in mappings if m["sku_id"] == "SKU-ARTIFACT-REGISTRY-STORAGE")
    egress = next(m for m in mappings if m["sku_id"] == "SKU-ARTIFACT-REGISTRY-EGRESS")

    assert storage["qty"] == 9.5
    assert egress["qty"] == 50.0


def test_estimate_artifact_registry_e2e(populated_artifact_registry_db: str) -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "repo-e2e",
                "service": "artifact_registry",
                "kind": "artifact_registry_repository",
                "region": "us-central1",
                "attributes": {
                    "storage_gb": 10.0,
                    "monthly_egress_gb": 50.0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_artifact_registry_db, model)
    assert est.monthly_total == pytest.approx(1.45, abs=1e-3)
    assert len(est.line_items) == 2
    assert any(li.component == "storage" for li in est.line_items)
    assert any(li.component == "egress" for li in est.line_items)
    assert len(est.unpriced) == 1
