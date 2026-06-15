# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import AttachedResource, Resource


def validate_appengine(
    r: Resource, errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP App Engine resources."""
    if r.kind == "app_engine_standard_version":
        iclass = r.attributes.get("instance_class", "F1")
        if iclass not in {"F1", "F2", "F4", "F4_1G", "B1", "B2", "B4", "B4_1G", "B8"}:
            errors.append(
                f"Resource '{r.resource_id}' has non-standard "
                f"instance class '{iclass}' for App Engine standard."
            )
    elif r.kind == "app_engine_flexible_version":
        for field in ("cpu", "memory_gb", "disk_gb"):
            if field in r.attributes:
                try:
                    float(r.attributes[field])
                except (ValueError, TypeError):
                    errors.append(
                        f"Resource '{r.resource_id}' has invalid '{field}' attribute."
                    )


def normalize_appengine(r: Resource) -> None:
    """Normalize GCP App Engine resources."""
    if r.kind == "app_engine_standard_version":
        if "instance_class" not in r.attributes:
            r.attributes["instance_class"] = "F1"
            r.assumptions.append("Defaulted instance_class to F1.")
        else:
            r.attributes["instance_class"] = str(r.attributes["instance_class"]).upper()

        free_tier_msg = (
            "App Engine standard includes a daily free tier per project "
            "(e.g. 28 hours for F-classes, 9 hours for B-classes) — "
            "not applied (list price only)."
        )
        if free_tier_msg not in r.assumptions:
            r.assumptions.append(free_tier_msg)

    elif r.kind == "app_engine_flexible_version":
        if "cpu" not in r.attributes:
            r.attributes["cpu"] = 1
        else:
            try:
                r.attributes["cpu"] = int(r.attributes["cpu"])
            except (ValueError, TypeError):
                r.attributes["cpu"] = 1

        if "memory_gb" not in r.attributes:
            r.attributes["memory_gb"] = 3.75
        else:
            try:
                r.attributes["memory_gb"] = float(r.attributes["memory_gb"])
            except (ValueError, TypeError):
                r.attributes["memory_gb"] = 3.75

        if "disk_gb" not in r.attributes:
            disk_gb = 10
            r.attributes["disk_gb"] = disk_gb
        else:
            try:
                disk_gb = int(r.attributes["disk_gb"])
                r.attributes["disk_gb"] = disk_gb
            except (ValueError, TypeError):
                disk_gb = 10
                r.attributes["disk_gb"] = disk_gb

        if not any(a.kind == "pd_persistent_disk" for a in r.attached):
            r.attached.append(
                AttachedResource(
                    kind="pd_persistent_disk", quantity=1, attributes={"size_gb": disk_gb}
                )
            )
