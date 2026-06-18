# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_armor(
    r: Resource, _errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Cloud Armor resources."""
    pass


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
