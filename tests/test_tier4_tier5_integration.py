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
def populated_tier4_tier5_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with mock SKUs for all Tier 4 and Tier 5 services."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    sku_files = [
        "cdn_skus.json",
        "dns_skus.json",
        "nat_skus.json",
        "vpc_skus.json",
        "armor_skus.json",
        "pubsub_skus.json",
        "dataflow_skus.json",
        "dataproc_skus.json",
    ]

    all_skus = []
    for sf in sku_files:
        with Path("tests/fixtures", sf).open() as f:
            all_skus.extend(json.load(f))

    # De-duplicate
    clean_skus = []
    seen_sku_ids = set()
    for s in all_skus:
        if s["sku_id"] != "METADATA-CITATION" and s["sku_id"] not in seen_sku_ids:
            clean_skus.append(s)
            seen_sku_ids.add(s["sku_id"])

    update_cache(temp_db_path, "gcp", clean_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


@pytest.fixture
def tier4_tier5_combined_model() -> ResourceModel:
    """Load the combined Tier 4 + 5 ResourceModel from the test plan JSON fixture."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser
    parser = TerraformPlanParser()
    return parser.parse("tests/fixtures/tier4_tier5_plan.json")


def test_tier4_tier5_full_plan_validation(tier4_tier5_combined_model: ResourceModel) -> None:
    """Verify that the combined model validates successfully."""
    res = validate_resource_model(tier4_tier5_combined_model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_tier4_tier5_full_plan_all_services_priced(
    populated_tier4_tier5_db: str, tier4_tier5_combined_model: ResourceModel
) -> None:
    """Verify that all standard Tier 4/5 resources are priced correctly in the integration test."""
    est = estimate_infrastructure(populated_tier4_tier5_db, tier4_tier5_combined_model)
    # CDN: 3.00, DNS: 0.60, NAT: 4.862, VPC: 3.65, Armor: 7.75, PubSub: 0.40, Dataflow: 58.3085, Dataproc: 97.35
    # Total = 175.9205
    assert pytest.approx(est.monthly_total, abs=1e-4) == 175.9205


def test_tier4_tier5_full_plan_disclaimer_present(
    populated_tier4_tier5_db: str, tier4_tier5_combined_model: ResourceModel
) -> None:
    """Verify that the disclaimer is present in the estimate."""
    est = estimate_infrastructure(populated_tier4_tier5_db, tier4_tier5_combined_model)
    assert est.disclaimer != ""


def test_tier4_tier5_pubsub_lite_resource_in_unpriced(
    populated_tier4_tier5_db: str, tier4_tier5_combined_model: ResourceModel
) -> None:
    """Verify that the Pub/Sub Lite topic resource is flagged in the unpriced list with a deprecation reason."""
    est = estimate_infrastructure(populated_tier4_tier5_db, tier4_tier5_combined_model)
    item = next(u for u in est.unpriced if u.resource_id == "google_pubsub_lite_topic.my_lite_topic")
    assert "deprecated" in item.reason.lower()


def test_tier4_tier5_dataproc_serverless_in_unpriced(
    populated_tier4_tier5_db: str, tier4_tier5_combined_model: ResourceModel
) -> None:
    """Verify that the Dataproc Serverless batch resource is flagged in the unpriced list."""
    est = estimate_infrastructure(populated_tier4_tier5_db, tier4_tier5_combined_model)
    item = next(u for u in est.unpriced if u.resource_id == "google_dataproc_serverless_batch.my_batch")
    assert "serverless" in item.reason.lower()


def test_tier4_tier5_internal_ip_in_unpriced(
    populated_tier4_tier5_db: str, tier4_tier5_combined_model: ResourceModel
) -> None:
    """Verify that the internal IP address resource is flagged in the unpriced list as free."""
    est = estimate_infrastructure(populated_tier4_tier5_db, tier4_tier5_combined_model)
    item = next(u for u in est.unpriced if u.resource_id == "google_compute_address.my_internal_ip")
    assert "free" in item.reason.lower()


def test_tier4_tier5_estimate_contains_all_eight_service_kinds(
    populated_tier4_tier5_db: str, tier4_tier5_combined_model: ResourceModel
) -> None:
    """Verify that the estimate includes line items representing all standard/priced service kinds."""
    est = estimate_infrastructure(populated_tier4_tier5_db, tier4_tier5_combined_model)
    resource_ids = {item.resource_id for item in est.line_items}
    # Expected standard resource ids parsed from tier4_tier5_plan.json
    expected_standard_ids = {
        "google_compute_backend_bucket.cdn_bucket",
        "google_dns_managed_zone.my_dns",
        "google_compute_router_nat.my_nat",
        "google_compute_address.my_external_ip",
        "google_compute_security_policy.my_policy",
        "google_pubsub_topic.my_topic",
        "google_dataflow_job.my_job",
        "google_dataproc_cluster.my_cluster",
    }
    assert expected_standard_ids.issubset(resource_ids)
