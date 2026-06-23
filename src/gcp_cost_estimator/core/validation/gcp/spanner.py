# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_spanner(
    r: Resource, errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Spanner resources."""
    if r.kind == "spanner_instance":
        edition = r.attributes.get("edition", "STANDARD")
        if edition not in {"STANDARD", "ENTERPRISE", "ENTERPRISE_PLUS"}:
            warnings.append(f"Resource '{r.resource_id}' has unrecognized edition '{edition}'.")
        config = r.attributes.get("config")
        if not config:
            warnings.append(f"Resource '{r.resource_id}' is missing config.")
        num_nodes = r.attributes.get("num_nodes")
        processing_units = r.attributes.get("processing_units")
        if num_nodes is not None and processing_units is not None:
            msg = f"Resource '{r.resource_id}' cannot specify both num_nodes and processing_units."
            errors.append(msg)


def normalize_spanner(r: Resource) -> None:
    """Normalize GCP Spanner resources."""
    if r.kind == "spanner_instance":
        edition = r.attributes.get("edition")
        if edition:
            edition_upper = str(edition).upper()
            if edition_upper not in {"STANDARD", "ENTERPRISE", "ENTERPRISE_PLUS"}:
                r.attributes["edition"] = "STANDARD"
                msg = (
                    "Defaulted edition to STANDARD "
                    f"(unrecognized edition '{edition}' was specified)."
                )
                r.assumptions.append(msg)
            else:
                r.attributes["edition"] = edition_upper
        else:
            r.attributes["edition"] = "STANDARD"
            r.assumptions.append("Defaulted edition to STANDARD.")

        num_nodes = r.attributes.get("num_nodes")
        processing_units = r.attributes.get("processing_units")

        if num_nodes is not None and processing_units is not None:
            pass
        elif num_nodes is not None:
            try:
                r.attributes["processing_units"] = int(num_nodes) * 1000
                msg = (
                    f"Converted num_nodes={num_nodes} to "
                    f"processing_units={r.attributes['processing_units']}."
                )
                r.assumptions.append(msg)
            except (ValueError, TypeError):
                r.attributes["processing_units"] = 100
                r.assumptions.append("Invalid num_nodes; defaulted processing_units to 100.")
        elif processing_units is not None:
            try:
                r.attributes["processing_units"] = int(processing_units)
            except (ValueError, TypeError):
                r.attributes["processing_units"] = 100
                msg = "Invalid processing_units; defaulted processing_units to 100."
                r.assumptions.append(msg)
        else:
            r.attributes["processing_units"] = 100
            r.assumptions.append("Defaulted processing_units to 100.")

        if "storage_gb" not in r.usage:
            r.usage["storage_gb"] = 0
            r.assumptions.append("Defaulted storage_gb to 0 GB.")
        else:
            try:
                r.usage["storage_gb"] = float(r.usage["storage_gb"])
            except (ValueError, TypeError):
                r.usage["storage_gb"] = 0
                r.assumptions.append("Invalid storage_gb; defaulted storage_gb to 0 GB.")

        config = r.attributes.get("config")
        if config:
            config_str = str(config).lower()
            if config_str.startswith("regional-"):
                config_type = "regional"
                mult = 1
            elif config_str in {"nam4", "eur4"}:
                config_type = "dual-region"
                mult = 2
            else:
                config_type = "multi-region"
                mult = 3
            r.attributes["config_type"] = config_type
            msg = f"Derived config_type={config_type} with storage multiplier {mult}x."
            r.assumptions.append(msg)

    if "runtime_hours_per_month" not in r.usage:
        r.usage["runtime_hours_per_month"] = 730
        r.assumptions.append("Defaulted runtime_hours_per_month to 730.")
