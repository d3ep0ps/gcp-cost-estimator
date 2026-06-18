# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.validate import validate_resource_model


def test_validate_vpc_invalid_type_raises() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vpc-addr",
                "service": "vpc",
                "kind": "compute_address",
                "region": "us-central1",
                "attributes": {
                    "address_type": "INVALID_TYPE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    assert any("address_type" in e for e in result["errors"])


def test_validate_vpc_internal_ip_is_unpriced() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vpc-addr",
                "service": "vpc",
                "kind": "compute_address",
                "region": "us-central1",
                "attributes": {
                    "address_type": "INTERNAL",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["unpriced"]) == 1
    assert "Internal static IPs are free" in result["unpriced"][0]["reason"]


def test_validate_vpc_mutual_exclusion_warning() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vpc-addr",
                "service": "vpc",
                "kind": "compute_address",
                "region": "us-central1",
                "attributes": {
                    "address_type": "EXTERNAL",
                },
                "usage": {
                    "on_spot_vm": True,
                    "on_forwarding_rule": True,
                }
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("mutually exclusive" in w for w in result["warnings"])


def test_validate_armor_negative_rules_raises() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "armor-policy",
                "service": "armor",
                "kind": "compute_security_policy",
                "region": "global",
                "attributes": {
                    "rule_count": -5,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    assert any("rule_count" in e for e in result["errors"])


def test_validate_armor_edge_is_unpriced() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "armor-policy",
                "service": "armor",
                "kind": "compute_security_policy",
                "region": "global",
                "attributes": {
                    "policy_type": "CLOUD_ARMOR_EDGE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["unpriced"]) == 1
    assert "Edge Security policies" in result["unpriced"][0]["reason"]


def test_validate_dns_invalid_visibility_raises() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dns-zone",
                "service": "dns",
                "kind": "dns_managed_zone",
                "region": "global",
                "attributes": {
                    "visibility": "INVALID",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    assert any("visibility" in e for e in result["errors"])


def test_validate_dns_private_is_unpriced() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dns-zone",
                "service": "dns",
                "kind": "dns_managed_zone",
                "region": "global",
                "attributes": {
                    "visibility": "private",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["unpriced"]) == 1
    assert "Private DNS zones are free" in result["unpriced"][0]["reason"]


def test_validate_dns_zero_queries_warns() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "dns-zone",
                "service": "dns",
                "kind": "dns_managed_zone",
                "region": "global",
                "attributes": {
                    "visibility": "public",
                },
                "usage": {
                    "monthly_queries": 0,
                }
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("cost will be $0" in w for w in result["warnings"])


def test_validate_nat_invalid_vms_or_ips_raises() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nat-gw",
                "service": "nat",
                "kind": "nat_gateway",
                "region": "us-central1",
                "usage": {
                    "num_vms": 0,
                    "num_nat_ips": 0,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert len(result["errors"]) >= 2


def test_validate_nat_high_ip_ratio_warns() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "nat-gw",
                "service": "nat",
                "kind": "nat_gateway",
                "region": "us-central1",
                "usage": {
                    "num_vms": 2,
                    "num_nat_ips": 6,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("IP-to-VM ratio" in w for w in result["warnings"])


def test_normalize_compute_applies_defaults_to_assumptions() -> None:
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "gce-vm",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {
                    "machine_type": "e2-medium",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    res = normalized.resources[0]
    assert res.usage["runtime_hours_per_month"] == 730
    assert res.attributes["disk_type"] == "pd-standard"
    assert any("runtime_hours_per_month" in a for a in res.assumptions)
    assert any("disk_type" in a for a in res.assumptions)
