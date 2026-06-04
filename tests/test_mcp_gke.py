# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.mcp.server import mcp

pytestmark = pytest.mark.anyio


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

    update_cache(temp_db_path, "gcp", gke_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


async def test_mcp_parse_terraform_extracts_gke() -> None:
    """Verify that calling the parse_terraform tool extracts GKE resources."""
    content, val = await mcp.call_tool(
        "parse_terraform", {"path": "tests/fixtures/terraform", "mode": "auto"}
    )
    assert content is not None
    assert val is not None
    assert "resources" in val

    resources = val["resources"]
    cluster = next(r for r in resources if r["resource_id"] == "google_container_cluster.minimal")
    assert cluster["provider"] == "gcp"
    assert cluster["service"] == "container"
    assert cluster["kind"] == "gke_cluster"


async def test_mcp_validate_resource_model_gke_defaults_applied() -> None:
    """Verify that calling validate_resource_model applies GKE defaults."""
    model_dict = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "gke-1",
                "service": "container",
                "kind": "gke_cluster",
                "region": "us-central1",
            }
        ]
    }
    content, val = await mcp.call_tool("validate_resource_model", {"model": model_dict})
    assert content is not None
    assert val["valid"] is True
    norm_res = val["normalized_model"]["resources"][0]
    assert norm_res["attributes"]["node_count"] == 3
    assert norm_res["attributes"]["machine_type"] == "e2-standard-4"
    assert norm_res["attributes"]["disk_size_gb"] == 100
    assert norm_res["attributes"]["disk_type"] == "pd-standard"


async def test_mcp_estimate_infrastructure_gke_e2e(populated_combined_db: str) -> None:
    """Verify that calling estimate_infrastructure tool with GKE resource returns a valid estimate."""
    model_dict = {
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
    with patch(
        "gcp_billing_mcp.mcp.server.get_default_db_path", return_value=populated_combined_db
    ):
        content, val = await mcp.call_tool("estimate_infrastructure", {"model": model_dict})
        assert content is not None
        assert val is not None
        assert "monthly_total" in val
        assert pytest.approx(val["monthly_total"], abs=1e-4) == 378.48628
        assert len(val["line_items"]) == 4
        assert len(val["unpriced"]) == 0
