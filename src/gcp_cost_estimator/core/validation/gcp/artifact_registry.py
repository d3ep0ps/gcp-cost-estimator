# SPDX-License-Identifier: Apache-2.0
"""Validation and normalisation for google_artifact_registry_repository resources."""
from __future__ import annotations

from typing import Any

from gcp_cost_estimator.core.model import Resource

VALID_FORMATS = {"DOCKER", "MAVEN", "NPM", "PYTHON", "APT", "YUM", "HELM", "GO", "GENERIC"}


def validate_artifact_registry(
    r: Resource,
    errors: list[str],
    warnings: list[str],
    unpriced: list[dict[str, Any]],
) -> None:
    """Validate a google_artifact_registry_repository resource."""
    fmt = str(r.attributes.get("format", "DOCKER")).upper()
    if fmt not in VALID_FORMATS:
        warnings.append(
            f"Resource '{r.resource_id}' has unknown Artifact Registry format '{fmt}'; "
            f"known formats: {sorted(VALID_FORMATS)}"
        )


def normalize_artifact_registry(r: Resource) -> None:
    """Normalise a google_artifact_registry_repository resource in-place."""
    if "format" in r.attributes:
        r.attributes["format"] = str(r.attributes["format"]).upper()
    if "location" in r.attributes:
        r.attributes["location"] = str(r.attributes["location"]).lower()
