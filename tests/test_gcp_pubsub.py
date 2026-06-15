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


def test_pubsub_topic_valid() -> None:
    """Verify topic is valid."""
    r = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        usage={"monthly_message_throughput_gb": 20.0},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_pubsub_subscription_valid() -> None:
    """Verify subscription is valid."""
    r = Resource(
        provider="gcp",
        resource_id="sub-1",
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
        attributes={"retain_acked_messages": True},
        usage={"subscription_storage_gb": 5.0},
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_pubsub_subscription_retain_acked_no_storage_default() -> None:
    """Verify subscription retain_acked_messages defaults to False."""
    r = Resource(
        provider="gcp",
        resource_id="sub-1",
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.attributes.get("retain_acked_messages") is False
    assert norm_r.usage.get("subscription_storage_gb") == 0.0


def test_pubsub_lite_resource_produces_unpriced_with_deprecation_reason() -> None:
    """Verify Pub/Sub Lite resources are flagged as unpriced with deprecation reason."""
    r = Resource(
        provider="gcp",
        resource_id="lite-topic",
        service="pubsub",
        kind="pubsub_lite_topic",
        region="global",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    assert len(res["unpriced"]) == 1
    assert "deprecated" in res["unpriced"][0]["reason"]


def test_pubsub_topic_throughput_default_applied() -> None:
    """Verify Pub/Sub throughput defaults are applied."""
    r = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
    )
    model = ResourceModel(resources=[r])
    res = validate_resource_model(model)
    assert res["valid"] is True
    norm_r = res["normalized_model"].resources[0]
    assert norm_r.usage.get("monthly_message_throughput_gb") == 10.0
    assert any("monthly_message_throughput_gb" in a for a in norm_r.assumptions)


@pytest.fixture
def populated_pubsub_db(temp_db_path: str) -> str:
    """Pre-populate temporary cache database with Pub/Sub SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/pubsub_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out metadata
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-10T12:00:00Z")
    return temp_db_path


def test_pubsub_throughput_priced(populated_pubsub_db: str) -> None:
    """Verify topic throughput is priced correctly."""
    r = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        usage={"monthly_message_throughput_gb": 10.0},
    )
    mapper = GcpSkuMapper(populated_pubsub_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "message_throughput")
    assert item["sku_id"] == "SKU-PUBSUB-THROUGHPUT"
    assert item["qty"] == 10.0
    assert item["unit_price"] == 0.04


def test_pubsub_subscription_storage_priced_when_retention_enabled(
    populated_pubsub_db: str,
) -> None:
    """Verify subscription storage is priced when retain_acked_messages is true."""
    r = Resource(
        provider="gcp",
        resource_id="sub-1",
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
        attributes={"retain_acked_messages": True},
        usage={"subscription_storage_gb": 5.0},
    )
    mapper = GcpSkuMapper(populated_pubsub_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    item = next(m for m in mappings if m["component"] == "retained_storage")
    assert item["sku_id"] == "SKU-PUBSUB-STORAGE"
    assert item["qty"] == 5.0
    assert item["unit_price"] == 0.27


def test_pubsub_subscription_storage_zero_when_retention_disabled(populated_pubsub_db: str) -> None:
    """Verify subscription storage is $0 when retain_acked_messages is false."""
    r = Resource(
        provider="gcp",
        resource_id="sub-1",
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
        attributes={"retain_acked_messages": False},
        usage={"subscription_storage_gb": 5.0},
    )
    mapper = GcpSkuMapper(populated_pubsub_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    # No retained storage mapping should be generated
    assert len(mappings) == 0


def test_pubsub_known_answer_10gb_throughput_no_storage(populated_pubsub_db: str) -> None:
    """Verify known-answer calculation for 10 GB throughput and no storage."""
    # 10 GB throughput = 10 * 0.04 = $0.40
    r = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        usage={"monthly_message_throughput_gb": 10.0},
    )
    mapper = GcpSkuMapper(populated_pubsub_db)
    mappings, unpriced = mapper.map_resource_to_skus(r)
    assert len(unpriced) == 0
    total = sum(m["qty"] * m["unit_price"] for m in mappings)
    assert round(total, 2) == 0.40


def test_pubsub_known_answer_10gb_throughput_5gb_storage(populated_pubsub_db: str) -> None:
    """Verify known-answer calculation for 10 GB throughput and 5 GB storage with retention."""
    # Topic: 10 GB throughput = 10 * 0.04 = $0.40
    # Sub: 5 GB storage * 0.27 = $1.35
    # Total = $1.75
    topic = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        usage={"monthly_message_throughput_gb": 10.0},
    )
    sub = Resource(
        provider="gcp",
        resource_id="sub-1",
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
        attributes={"retain_acked_messages": True},
        usage={"subscription_storage_gb": 5.0},
    )
    mapper = GcpSkuMapper(populated_pubsub_db)
    t_mappings, t_unpriced = mapper.map_resource_to_skus(topic)
    s_mappings, s_unpriced = mapper.map_resource_to_skus(sub)
    assert len(t_unpriced) == 0 and len(s_unpriced) == 0
    total = sum(m["qty"] * m["unit_price"] for m in (t_mappings + s_mappings))
    assert round(total, 2) == 1.75


def test_terraform_hcl_parses_google_pubsub_topic() -> None:
    """Verify HCL parser resolves google_pubsub_topic resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_pubsub_topic.my_topic")
    assert res.provider == "gcp"
    assert res.service == "pubsub"
    assert res.kind == "pubsub_topic"
    assert res.region == "global"


def test_terraform_hcl_parses_google_pubsub_subscription_with_retention() -> None:
    """Verify HCL parser resolves google_pubsub_subscription resource."""
    from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser

    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")
    res = next(r for r in model.resources if r.resource_id == "google_pubsub_subscription.my_sub")
    assert res.provider == "gcp"
    assert res.service == "pubsub"
    assert res.kind == "pubsub_subscription"
    assert res.attributes.get("retain_acked_messages") is True


def test_terraform_plan_json_pubsub_topic_parsed() -> None:
    """Verify plan JSON parser resolves pubsub_topic resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/pubsub_plan.json")
    res = next(r for r in model.resources if r.resource_id == "google_pubsub_topic.my_topic")
    assert res.provider == "gcp"
    assert res.service == "pubsub"
    assert res.kind == "pubsub_topic"
    assert res.region == "global"


def test_terraform_plan_json_pubsub_subscription_parsed() -> None:
    """Verify plan JSON parser resolves pubsub_subscription resource."""
    from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser

    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/pubsub_plan.json")
    res = next(r for r in model.resources if r.resource_id == "google_pubsub_subscription.my_sub")
    assert res.provider == "gcp"
    assert res.service == "pubsub"
    assert res.kind == "pubsub_subscription"
    assert res.attributes.get("retain_acked_messages") is True


def test_pubsub_estimate_includes_disclaimer(populated_pubsub_db: str) -> None:
    """Verify the Pub/Sub estimate output includes standard disclaimer."""
    topic = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        usage={"monthly_message_throughput_gb": 10.0},
    )
    model = ResourceModel(resources=[topic])
    est = estimate_infrastructure(populated_pubsub_db, model)
    assert est.disclaimer != ""


def test_pubsub_topic_and_subscription_separate_line_items(populated_pubsub_db: str) -> None:
    """Verify topic and subscription are estimated as separate line items."""
    topic = Resource(
        provider="gcp",
        resource_id="topic-1",
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        usage={"monthly_message_throughput_gb": 10.0},
    )
    sub = Resource(
        provider="gcp",
        resource_id="sub-1",
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
        attributes={"retain_acked_messages": True},
        usage={"subscription_storage_gb": 5.0},
    )
    model = ResourceModel(resources=[topic, sub])
    est = estimate_infrastructure(populated_pubsub_db, model)
    assert len(est.line_items) == 2
    assert est.line_items[0].resource_id == "topic-1"
    assert est.line_items[1].resource_id == "sub-1"


def test_pubsub_lite_resource_in_estimate_produces_unpriced_entry(populated_pubsub_db: str) -> None:
    """Verify Pub/Sub Lite resources end up in the unpriced list of the estimate."""
    lite = Resource(
        provider="gcp",
        resource_id="lite-topic",
        service="pubsub",
        kind="pubsub_lite_topic",
        region="global",
    )
    model = ResourceModel(resources=[lite])
    est = estimate_infrastructure(populated_pubsub_db, model)
    assert len(est.unpriced) == 1
    assert est.unpriced[0].resource_id == "lite-topic"
    assert "deprecated" in est.unpriced[0].reason
