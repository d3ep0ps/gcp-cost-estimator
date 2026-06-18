# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_armor(
    r: Resource, errors: list[str], warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Cloud Armor resources."""
    if r.kind == "compute_security_policy":
        rule_count = r.attributes.get("rule_count", 0)
        if rule_count < 0:
            errors.append("rule_count must be non-negative.")

        policy_type = r.attributes.get("type") or r.attributes.get("policy_type")
        if policy_type == "CLOUD_ARMOR_EDGE":
            unpriced.append({
                "resource_id": r.resource_id,
                "reason": "Edge Security policies have different pricing not yet modelled."
            })

        monthly_requests = r.usage.get("monthly_requests", 1000000)
        if monthly_requests > 1_000_000_000:
            warnings.append("monthly_requests exceeds 1 billion (likely unit/scale confusion).")


def normalize_armor(r: Resource) -> None:
    """Normalize GCP Cloud Armor resources."""
    if r.kind == "compute_security_policy":
        if "rule_count" not in r.attributes:
            r.attributes["rule_count"] = 0
        else:
            try:
                r.attributes["rule_count"] = int(r.attributes["rule_count"])
            except ValueError, TypeError:
                r.attributes["rule_count"] = 0

        if "monthly_requests" not in r.usage:
            r.usage["monthly_requests"] = 1000000
            r.assumptions.append("Defaulted monthly_requests to 1000000.")
        else:
            try:
                r.usage["monthly_requests"] = int(float(r.usage["monthly_requests"]))
            except ValueError, TypeError:
                r.usage["monthly_requests"] = 1000000
                r.assumptions.append("Invalid monthly_requests; defaulted to 1000000.")
