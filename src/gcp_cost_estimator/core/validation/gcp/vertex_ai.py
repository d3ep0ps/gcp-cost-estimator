# SPDX-License-Identifier: Apache-2.0
"""Validation and normalisation for Vertex AI resources."""
from __future__ import annotations

from typing import Any

from gcp_cost_estimator.core.model import Resource

_SUPPORTED_LOCATIONS = {
    "us-central1", "us-east1", "us-east4", "us-west1",
    "europe-west1", "europe-west2", "europe-west4",
    "asia-east1", "asia-northeast1", "asia-southeast1",
}


def validate_vertex_ai_endpoint(
    r: Resource,
    errors: list[str],
    warnings: list[str],
    unpriced: list[dict[str, Any]],
) -> None:
    """Validate a google_vertex_ai_endpoint resource."""
    dedicated = r.attributes.get("dedicated_endpoint_enabled", False)
    if not dedicated:
        unpriced.append({
            "resource_id": r.resource_id,
            "reason": (
                "Vertex AI shared endpoint: inference costs depend on deployed model "
                "machine type and traffic, which are not declared in this Terraform resource. "
                "See https://cloud.google.com/vertex-ai/pricing#prediction-and-explanation"
            ),
        })

    loc = r.attributes.get("location", "")
    if loc and loc.lower() not in _SUPPORTED_LOCATIONS:
        warnings.append(
            f"Resource '{r.resource_id}' location '{loc}' is not in the known Vertex AI region list; "
            "pricing may fall back to us-central1 rates."
        )


def normalize_vertex_ai_endpoint(r: Resource) -> None:
    """Normalise a google_vertex_ai_endpoint resource in-place."""
    if "location" in r.attributes:
        r.attributes["location"] = str(r.attributes["location"]).lower()
    if "dedicated_endpoint_enabled" not in r.attributes:
        r.attributes["dedicated_endpoint_enabled"] = False
