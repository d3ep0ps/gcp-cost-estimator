# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_alloydb(
    r: Resource, errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP AlloyDB resources."""
    if r.kind == "alloydb_instance":
        if "cpu_count" not in r.attributes:
            errors.append(f"Resource '{r.resource_id}' is missing cpu_count attribute.")
        else:
            cpu_count = r.attributes.get("cpu_count")
            if cpu_count is None:
                errors.append(f"Resource '{r.resource_id}' cpu_count cannot be null.")
            else:
                try:
                    cpu_val = int(cpu_count)
                    if cpu_val not in {2, 4, 8, 16, 32, 64, 96, 128}:
                        msg = f"Resource '{r.resource_id}' has unsupported vcpu count '{cpu_val}'."
                        warnings.append(msg)
                except (ValueError, TypeError):
                    errors.append(f"Resource '{r.resource_id}' cpu_count must be an integer.")


def normalize_alloydb(r: Resource) -> None:
    """Normalize GCP AlloyDB resources."""
    if r.kind == "alloydb_cluster":
        if "storage_gb" not in r.usage:
            r.usage["storage_gb"] = 100
            r.assumptions.append("Defaulted storage_gb to 100.")
        else:
            try:
                r.usage["storage_gb"] = float(r.usage["storage_gb"])
            except (ValueError, TypeError):
                r.usage["storage_gb"] = 100
                r.assumptions.append("Invalid storage_gb; defaulted to 100.")

        if "backup_enabled" not in r.usage:
            r.usage["backup_enabled"] = False
            r.assumptions.append("Defaulted backup_enabled to False.")
        else:
            if isinstance(r.usage["backup_enabled"], str):
                r.usage["backup_enabled"] = r.usage["backup_enabled"].lower() == "true"
            else:
                r.usage["backup_enabled"] = bool(r.usage["backup_enabled"])

    elif r.kind == "alloydb_instance":
        if "instance_type" not in r.attributes:
            r.attributes["instance_type"] = "PRIMARY"
            r.assumptions.append("Defaulted instance_type to PRIMARY.")
        else:
            itype = str(r.attributes["instance_type"]).upper()
            if itype not in {"PRIMARY", "READ_POOL"}:
                r.attributes["instance_type"] = "PRIMARY"
                msg = (
                    "Defaulted instance_type to PRIMARY "
                    f"(unrecognized instance_type '{itype}' was specified)."
                )
                r.assumptions.append(msg)
            else:
                r.attributes["instance_type"] = itype

        if r.attributes["instance_type"] == "READ_POOL":
            if "node_count" not in r.attributes:
                r.attributes["node_count"] = 1
                r.assumptions.append("Defaulted node_count to 1 for READ_POOL instance.")
            else:
                try:
                    r.attributes["node_count"] = int(r.attributes["node_count"])
                except (ValueError, TypeError):
                    r.attributes["node_count"] = 1
                    r.assumptions.append("Invalid node_count; defaulted to 1.")

    # Both cluster and instance resources have runtime billed by the hour
    if "runtime_hours_per_month" not in r.usage:
        r.usage["runtime_hours_per_month"] = 730
        r.assumptions.append("Defaulted runtime_hours_per_month to 730.")
