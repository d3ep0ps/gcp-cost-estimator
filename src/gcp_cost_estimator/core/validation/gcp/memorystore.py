# SPDX-License-Identifier: Apache-2.0

import contextlib
from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_memorystore(
    r: Resource, errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Memorystore resources."""
    if r.kind == "redis_instance":
        if "memory_size_gb" not in r.attributes:
            errors.append(f"Resource '{r.resource_id}' is missing memory_size_gb attribute.")
    elif r.kind == "memorystore_instance":
        node_type = r.attributes.get("node_type")
        valid_types = {
            "SHARED_CORE_NANO",
            "STANDARD_SMALL",
            "HIGHMEM_MEDIUM",
            "HIGHMEM_XLARGE",
        }
        if node_type and node_type not in valid_types:
            warnings.append(f"Resource '{r.resource_id}' has unrecognized node_type '{node_type}'.")


def normalize_memorystore(r: Resource) -> None:
    """Normalize GCP Memorystore resources."""
    if r.kind == "redis_instance":
        if "tier" not in r.attributes:
            r.attributes["tier"] = "BASIC"
            r.assumptions.append("Defaulted tier to BASIC.")
        else:
            tier_val = str(r.attributes["tier"]).upper()
            if tier_val not in {"BASIC", "STANDARD_HA"}:
                r.attributes["tier"] = "BASIC"
                msg = f"Defaulted tier to BASIC (unrecognized tier '{tier_val}' was specified)."
                r.assumptions.append(msg)
            else:
                r.attributes["tier"] = tier_val

        if "memory_size_gb" in r.attributes:
            with contextlib.suppress(ValueError, TypeError):
                r.attributes["memory_size_gb"] = float(r.attributes["memory_size_gb"])

    elif r.kind == "memorystore_instance":
        if "shard_count" not in r.attributes:
            r.attributes["shard_count"] = 1
            r.assumptions.append("Defaulted shard_count to 1.")
        else:
            try:
                r.attributes["shard_count"] = int(r.attributes["shard_count"])
            except ValueError, TypeError:
                r.attributes["shard_count"] = 1
                r.assumptions.append("Invalid shard_count; defaulted to 1.")

        if "mode" not in r.attributes:
            r.attributes["mode"] = "STANDALONE"
            r.assumptions.append("Defaulted mode to STANDALONE.")
        else:
            mode_val = str(r.attributes["mode"]).upper()
            if mode_val not in {"STANDALONE", "CLUSTER"}:
                r.attributes["mode"] = "STANDALONE"
                msg = (
                    f"Defaulted mode to STANDALONE (unrecognized mode '{mode_val}' was specified)."
                )
                r.assumptions.append(msg)
            else:
                r.attributes["mode"] = mode_val

    if "runtime_hours_per_month" not in r.usage:
        r.usage["runtime_hours_per_month"] = 730
        r.assumptions.append("Defaulted runtime_hours_per_month to 730.")
