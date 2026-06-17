# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_dns(
    r: Resource, _errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP DNS resources."""
    pass


def normalize_dns(r: Resource) -> None:
    """Normalize GCP DNS resources."""
    if r.kind == "dns_managed_zone":
        if "visibility" not in r.attributes:
            r.attributes["visibility"] = "public"
            r.assumptions.append("Defaulted visibility to public.")
        else:
            r.attributes["visibility"] = str(r.attributes["visibility"]).lower()

        if "monthly_queries" not in r.usage:
            r.usage["monthly_queries"] = 1000000
            r.assumptions.append("Defaulted monthly_queries to 1000000.")
        else:
            try:
                r.usage["monthly_queries"] = int(float(r.usage["monthly_queries"]))
            except ValueError, TypeError:
                r.usage["monthly_queries"] = 1000000
                r.assumptions.append("Invalid monthly_queries; defaulted to 1000000.")
