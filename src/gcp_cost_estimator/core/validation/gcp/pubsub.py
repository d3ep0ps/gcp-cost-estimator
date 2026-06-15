# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_pubsub(
    r: Resource, _errors: list[str], _warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Pub/Sub resources."""
    if "lite" in str(r.kind).lower():
        unpriced.append(
            {
                "resource_id": r.resource_id,
                "reason": "Pub/Sub Lite was deprecated on 2026-03-18",
            }
        )


def normalize_pubsub(r: Resource) -> None:
    """Normalize GCP Pub/Sub resources."""
    if r.kind == "pubsub_topic":
        if "monthly_message_throughput_gb" not in r.usage:
            r.usage["monthly_message_throughput_gb"] = 10.0
            r.assumptions.append("Defaulted monthly_message_throughput_gb to 10.0 GB.")
        else:
            try:
                r.usage["monthly_message_throughput_gb"] = float(
                    r.usage["monthly_message_throughput_gb"]
                )
            except (ValueError, TypeError):
                r.usage["monthly_message_throughput_gb"] = 10.0
                r.assumptions.append(
                    "Invalid monthly_message_throughput_gb; defaulted to 10.0 GB."
                )
        r.assumptions.append("First 10 GiB/month free is not applied.")
    elif r.kind == "pubsub_subscription":
        if "retain_acked_messages" not in r.attributes:
            r.attributes["retain_acked_messages"] = False
        else:
            if isinstance(r.attributes["retain_acked_messages"], str):
                r.attributes["retain_acked_messages"] = r.attributes[
                    "retain_acked_messages"
                ].lower() in {"true", "1", "yes"}
            else:
                r.attributes["retain_acked_messages"] = bool(
                    r.attributes["retain_acked_messages"]
                )

        if "subscription_storage_gb" not in r.usage:
            r.usage["subscription_storage_gb"] = 0.0
            r.assumptions.append("Defaulted subscription_storage_gb to 0.0 GB.")
        else:
            try:
                r.usage["subscription_storage_gb"] = float(
                    r.usage["subscription_storage_gb"]
                )
            except (ValueError, TypeError):
                r.usage["subscription_storage_gb"] = 0.0
                r.assumptions.append(
                    "Invalid subscription_storage_gb; defaulted to 0.0 GB."
                )
