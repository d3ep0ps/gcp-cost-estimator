# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_bigquery(
    r: Resource, _errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP BigQuery resources."""
    if r.kind == "bigquery_dataset":
        pricing_model = r.attributes.get("pricing_model")
        if pricing_model == "capacity":
            warnings.append(
                f"Resource '{r.resource_id}' specifies capacity-based pricing, "
                "which is not supported in v1."
            )


def normalize_bigquery(r: Resource) -> None:
    """Normalize GCP BigQuery resources."""
    if r.kind == "bigquery_dataset":
        if "active_storage_gb" not in r.usage:
            r.usage["active_storage_gb"] = 100
            r.assumptions.append(
                "Defaulted active_storage_gb to 100 GB. Override usage.active_storage_gb "
                "with your dataset size."
            )
        else:
            try:
                r.usage["active_storage_gb"] = float(r.usage["active_storage_gb"])
            except (ValueError, TypeError):
                r.usage["active_storage_gb"] = 100
                r.assumptions.append(
                    "Invalid active_storage_gb specified; "
                    "defaulted active_storage_gb to 100 GB."
                )

        if "long_term_storage_gb" not in r.usage:
            r.usage["long_term_storage_gb"] = 0
            r.assumptions.append(
                "Defaulted long_term_storage_gb to 0 GB. Set usage.long_term_storage_gb "
                "for data unmodified >90 days."
            )
        else:
            try:
                r.usage["long_term_storage_gb"] = float(r.usage["long_term_storage_gb"])
            except (ValueError, TypeError):
                r.usage["long_term_storage_gb"] = 0

        if "monthly_query_tb" not in r.usage:
            r.usage["monthly_query_tb"] = 1
            r.assumptions.append(
                "Defaulted monthly_query_tb to 1 TB. Override usage.monthly_query_tb "
                "with your expected query volume."
            )
        else:
            try:
                r.usage["monthly_query_tb"] = float(r.usage["monthly_query_tb"])
            except (ValueError, TypeError):
                r.usage["monthly_query_tb"] = 1

        if "monthly_streaming_gb" not in r.usage:
            r.usage["monthly_streaming_gb"] = 0
            r.assumptions.append(
                "Defaulted monthly_streaming_gb to 0 GB. Set usage.monthly_streaming_gb "
                "if using the legacy Streaming API."
            )
        else:
            try:
                r.usage["monthly_streaming_gb"] = float(r.usage["monthly_streaming_gb"])
            except (ValueError, TypeError):
                r.usage["monthly_streaming_gb"] = 0

        free_tier_assumption = (
            "Free tier (10 GB storage, 1 TB queries/month) not applied — list price only."
        )
        if free_tier_assumption not in r.assumptions:
            r.assumptions.append(free_tier_assumption)
