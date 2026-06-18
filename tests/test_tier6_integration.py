# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
from gcp_cost_estimator.core.pricing.cache import init_db, update_cache
from gcp_cost_estimator.core.service import estimate_infrastructure


@pytest.fixture
def populated_tier6_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static fixtures for all Tier 6 services."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    # Load and combine all three SKU lists
    all_skus = []
    for fixture_file in (
        "filestore_skus.json",
        "vertex_ai_skus.json",
        "artifact_registry_skus.json",
    ):
        with Path("tests/fixtures", fixture_file).open() as f:
            skus = json.load(f)
        all_skus.extend([s for s in skus if s["sku_id"] != "METADATA-CITATION"])

    update_cache(temp_db_path, "gcp", all_skus, "2026-06-15T12:00:00Z")
    return temp_db_path


def test_tier6_combined_estimate(populated_tier6_db: str) -> None:
    """FR-5: Combined estimate for all three Tier 6 services (Filestore, Vertex AI, Artifact Registry)."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/tier6_plan.json")

    # Run the end-to-end estimation
    est = estimate_infrastructure(populated_tier6_db, model)

    # 1. Total cost validation:
    # Total expected: 163.8399 + 79.935 + 0.95 = 244.7249
    assert est.monthly_total == pytest.approx(244.725, abs=1e-2)

    # 2. Check line items
    assert len(est.line_items) == 3
    components = {li.component for li in est.line_items}
    assert "compute" in components
    assert "storage" in components

    # 3. Check unpriced dimensions
    unpriced_reasons = {up.reason for up in est.unpriced}
    assert any("backup storage pricing not modelled" in r for r in unpriced_reasons)
    assert any("inference traffic costs" in r for r in unpriced_reasons)
    assert any("vulnerability scanning" in r for r in unpriced_reasons)

    # 4. Check assumptions
    assert len(est.assumptions) > 0
    # Make sure defaults/assumptions are recorded
    assert any("Defaulted runtime" in a for a in est.assumptions)
