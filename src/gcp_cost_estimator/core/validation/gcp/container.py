# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_container(
    r: Resource, _errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP GKE resources."""
    if r.kind in {"gke_cluster", "gke_node_pool"}:
        is_autopilot = r.attributes.get("enable_autopilot", False)
        if not is_autopilot:
            mtype = r.attributes.get("machine_type")
            if not mtype:
                warnings.append(
                    f"Resource '{r.resource_id}' is missing machine_type; "
                    "defaulting to 'e2-standard-4'."
                )


def normalize_container(r: Resource) -> None:
    """Normalize GCP GKE resources."""
    if r.kind in {"gke_cluster", "gke_node_pool"}:
        is_autopilot = r.attributes.get("enable_autopilot", False)
        if not is_autopilot:
            if "node_count" not in r.attributes:
                r.attributes["node_count"] = 3
                r.assumptions.append("Defaulted node_count to 3.")
            else:
                try:
                    r.attributes["node_count"] = int(r.attributes["node_count"])
                except ValueError, TypeError:
                    r.attributes["node_count"] = 3
                    r.assumptions.append("Invalid node_count; defaulted node_count to 3.")

            if "machine_type" not in r.attributes:
                r.attributes["machine_type"] = "e2-standard-4"
                r.assumptions.append("Defaulted machine_type to e2-standard-4.")

            if "disk_size_gb" not in r.attributes:
                r.attributes["disk_size_gb"] = 100
                r.assumptions.append("Defaulted disk_size_gb to 100.")
            else:
                try:
                    r.attributes["disk_size_gb"] = int(r.attributes["disk_size_gb"])
                except ValueError, TypeError:
                    r.attributes["disk_size_gb"] = 100
                    r.assumptions.append("Invalid disk_size_gb; defaulted disk_size_gb to 100.")

            if "disk_type" not in r.attributes:
                r.attributes["disk_type"] = "pd-standard"
                r.assumptions.append("Defaulted disk_type to pd-standard.")
