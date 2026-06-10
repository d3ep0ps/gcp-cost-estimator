# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.iac.terraform_hcl import TerraformHclParser
from gcp_cost_estimator.core.iac.terraform_plan import TerraformPlanParser


def test_hcl_parses_google_redis_instance_basic() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_redis_instance.redis_basic")
    assert res.provider == "gcp"
    assert res.service == "memorystore"
    assert res.kind == "redis_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["memory_size_gb"]) == 5
    assert res.attributes["tier"] == "BASIC"


def test_hcl_parses_google_redis_instance_standard_ha() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_redis_instance.redis_ha")
    assert res.provider == "gcp"
    assert res.service == "memorystore"
    assert res.kind == "redis_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["memory_size_gb"]) == 10
    assert res.attributes["tier"] == "STANDARD_HA"


def test_hcl_parses_google_memorystore_instance_standalone() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r
        for r in model.resources
        if r.resource_id == "google_memorystore_instance.valkey_standalone"
    )
    assert res.provider == "gcp"
    assert res.service == "memorystore"
    assert res.kind == "memorystore_instance"
    assert res.region == "us-central1"  # location attribute
    assert res.attributes["node_type"] == "SHARED_CORE_NANO"
    assert res.attributes["mode"] == "STANDALONE"


def test_hcl_parses_google_memorystore_instance_cluster() -> None:
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_memorystore_instance.valkey_cluster"
    )
    assert res.provider == "gcp"
    assert res.service == "memorystore"
    assert res.kind == "memorystore_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["shard_count"]) == 3
    assert res.attributes["node_type"] == "STANDARD_SMALL"
    assert res.attributes["mode"] == "CLUSTER"


def test_plan_json_resolves_google_redis_instance() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/redis_plan.json")

    res = next(r for r in model.resources if r.resource_id == "google_redis_instance.redis_basic")
    assert res.provider == "gcp"
    assert res.service == "memorystore"
    assert res.kind == "redis_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["memory_size_gb"]) == 5
    assert res.attributes["tier"] == "BASIC"


def test_plan_json_resolves_google_memorystore_instance() -> None:
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/memorystore_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_memorystore_instance.valkey_cluster"
    )
    assert res.provider == "gcp"
    assert res.service == "memorystore"
    assert res.kind == "memorystore_instance"
    assert res.region == "us-central1"
    assert int(res.attributes["shard_count"]) == 3
    assert res.attributes["node_type"] == "STANDARD_SMALL"
    assert res.attributes["mode"] == "CLUSTER"
