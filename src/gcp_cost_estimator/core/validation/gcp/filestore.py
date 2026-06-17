# SPDX-License-Identifier: Apache-2.0
"""Validation and normalisation for google_filestore_instance resources."""

from __future__ import annotations

import contextlib
from typing import Any

from gcp_cost_estimator.core.model import Resource

VALID_TIERS = {"BASIC_HDD", "BASIC_SSD", "ZONAL", "REGIONAL", "ENTERPRISE", "HIGH_SCALE_SSD"}

# Minimum capacity in GiB per tier
# Source: https://cloud.google.com/filestore/docs/service-tiers (verified 2026-06-15)
TIER_MIN_GB: dict[str, int] = {
    "BASIC_HDD": 1024,
    "BASIC_SSD": 2560,
    "ZONAL": 1024,
    "REGIONAL": 1024,
    "ENTERPRISE": 1024,
    "HIGH_SCALE_SSD": 10240,
}


def validate_filestore(
    r: Resource,
    errors: list[str],
    warnings: list[str],
    unpriced: list[dict[str, Any]],
) -> None:
    """Validate a google_filestore_instance resource."""
    tier = str(r.attributes.get("tier", "BASIC_HDD")).upper()
    if tier not in VALID_TIERS:
        errors.append(
            f"Resource '{r.resource_id}' has invalid Filestore tier '{tier}'; "
            f"must be one of {sorted(VALID_TIERS)}"
        )

    capacity_gb = r.attributes.get("capacity_gb")
    if capacity_gb is not None:
        try:
            gb = float(capacity_gb)
        except TypeError, ValueError:
            errors.append(
                f"Resource '{r.resource_id}' capacity_gb must be a number; got {capacity_gb!r}"
            )
            gb = None
        if gb is not None and tier in TIER_MIN_GB and gb < TIER_MIN_GB[tier]:
            warnings.append(
                f"Resource '{r.resource_id}' capacity_gb {gb} GiB is below tier minimum "
                f"{TIER_MIN_GB[tier]} GiB for {tier}."
            )

    if r.attributes.get("custom_performance_enabled"):
        unpriced.append(
            {
                "resource_id": r.resource_id,
                "reason": (
                    "Filestore Custom Performance (provisioned IOPS) pricing not modelled; "
                    "see https://cloud.google.com/filestore/docs/custom-performance"
                ),
            }
        )


def normalize_filestore(r: Resource) -> None:
    """Normalise a google_filestore_instance resource in-place."""
    if "tier" in r.attributes:
        r.attributes["tier"] = str(r.attributes["tier"]).upper()
    else:
        r.attributes["tier"] = "BASIC_HDD"
        r.assumptions.append("Defaulted tier to BASIC_HDD.")

    if "capacity_gb" in r.attributes:
        with contextlib.suppress(TypeError, ValueError):
            r.attributes["capacity_gb"] = float(r.attributes["capacity_gb"])
    else:
        r.attributes["capacity_gb"] = 1024.0
        r.assumptions.append("Defaulted capacity_gb to 1024 GiB.")
