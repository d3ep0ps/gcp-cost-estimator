# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_dns(
    r: Resource, errors: list[str], warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP DNS resources."""
    if r.kind == "dns_managed_zone":
        visibility = r.attributes.get("visibility", "public")
        if visibility:
            visibility_lower = str(visibility).lower()
            if visibility_lower not in ("public", "private"):
                errors.append(f"Unrecognized visibility '{visibility}' for dns_managed_zone.")
            elif visibility_lower == "private":
                unpriced.append(
                    {
                        "resource_id": r.resource_id,
                        "reason": "Private DNS zones are free; no billing line item.",
                    }
                )

        queries = r.usage.get("monthly_queries", 1000000)
        if queries < 0:
            errors.append("monthly_queries must be non-negative.")
        elif queries == 0:
            warnings.append("monthly_queries is 0; cost will be $0.")


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
