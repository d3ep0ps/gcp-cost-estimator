# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_vpc(
    r: Resource, errors: list[str], warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP VPC resources."""
    pass


def normalize_vpc(r: Resource) -> None:
    """Normalize GCP VPC resources."""
    if r.kind == "compute_address":
        addr_type = r.attributes.get("address_type", "EXTERNAL")
        r.attributes["address_type"] = str(addr_type).upper()

        for field, val in [
            ("in_use", True),
            ("on_spot_vm", False),
            ("on_forwarding_rule", False),
        ]:
            if field not in r.usage:
                r.usage[field] = val
                r.assumptions.append(f"Defaulted {field} to {val}.")
            else:
                if isinstance(r.usage[field], str):
                    r.usage[field] = r.usage[field].lower() in {"true", "1", "yes"}
                else:
                    r.usage[field] = bool(r.usage[field])
