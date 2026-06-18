# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_compute(
    r: Resource, errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP compute resources."""
    if r.kind == "gce_instance":
        mtype = r.attributes.get("machine_type")
        if not mtype:
            errors.append(
                f"Resource '{r.resource_id}' is a GCE instance but "
                "has no valid machine_type attribute."
            )


def normalize_compute(r: Resource) -> None:
    """Normalize GCP compute resources."""
    if r.kind == "gce_instance":
        # Outer loop in validate.py defaults runtime_hours_per_month. We check if it was defaulted.
        if "Defaulted runtime to 730 hours/month." in r.assumptions or "runtime_hours_per_month" not in r.usage:
            r.usage["runtime_hours_per_month"] = 730
            msg = "Defaulted runtime_hours_per_month to 730."
            if msg not in r.assumptions:
                r.assumptions.append(msg)
        else:
            try:
                r.usage["runtime_hours_per_month"] = float(r.usage["runtime_hours_per_month"])
            except ValueError, TypeError:
                r.usage["runtime_hours_per_month"] = 730
                r.assumptions.append("Invalid runtime_hours_per_month; defaulted to 730.")

        if "disk_type" not in r.attributes:
            r.attributes["disk_type"] = "pd-standard"
            r.assumptions.append("Defaulted disk_type to pd-standard.")
