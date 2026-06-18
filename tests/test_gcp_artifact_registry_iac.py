# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.service import estimate_infrastructure


@pytest.fixture
def populated_artifact_registry_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Artifact Registry SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/artifact_registry_skus.json").open() as f:
        mock_skus = json.load(f)

    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]
    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-15T12:00:00Z")
    return temp_db_path


def test_hcl_parses_google_artifact_registry_repository() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_artifact_registry_repository.docker_repo"
    )
    assert res.provider == "gcp"
    assert res.service == "artifact"
    assert res.kind == "google_artifact_registry_repository"
    assert res.region == "us-central1"
    assert res.attributes["format"] == "DOCKER"


def test_plan_json_resolves_google_artifact_registry_repository() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/artifact_registry_plan.json")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_artifact_registry_repository.docker_repo"
    )
    assert res.provider == "gcp"
    assert res.service == "artifact"
    assert res.kind == "google_artifact_registry_repository"
    assert res.region == "us-central1"
    assert res.attributes["format"] == "DOCKER"


def test_artifact_registry_roundtrip_plan_to_estimate(populated_artifact_registry_db: str) -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/artifact_registry_plan.json")

    # Estimate infrastructure (will apply default 10 GB storage -> (10.0 - 0.5) * 0.10 = $0.95)
    est = estimate_infrastructure(populated_artifact_registry_db, model)

    # Check that the specific line item for Artifact Registry exists
    ar_items = [li for li in est.line_items if li.sku_id == "SKU-ARTIFACT-REGISTRY-STORAGE"]
    assert len(ar_items) == 1
    assert ar_items[0].monthly_cost == pytest.approx(0.95, abs=1e-3)
