# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_vpc(
    r: Resource, errors: list[str], warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP VPC resources."""
    if r.kind == "compute_address":
        addr_type = r.attributes.get("address_type", "EXTERNAL")
        if addr_type:
            addr_type_upper = str(addr_type).upper()
            if addr_type_upper not in ("EXTERNAL", "INTERNAL"):
                errors.append(f"Unrecognized address_type '{addr_type}' for compute_address.")
            elif addr_type_upper == "INTERNAL":
                unpriced.append(
                    {
                        "resource_id": r.resource_id,
                        "reason": "Internal static IPs are free; no billing line item.",
                    }
                )

        on_spot_vm = r.usage.get("on_spot_vm", False)
        on_forwarding_rule = r.usage.get("on_forwarding_rule", False)
        if on_spot_vm and on_forwarding_rule:
            warnings.append("on_spot_vm and on_forwarding_rule are mutually exclusive.")


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
