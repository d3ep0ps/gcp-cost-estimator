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
    pass
