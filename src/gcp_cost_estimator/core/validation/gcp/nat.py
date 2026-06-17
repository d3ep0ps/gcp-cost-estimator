# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_nat(
    r: Resource, errors: list[str], warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP NAT resources."""
    pass


def normalize_nat(r: Resource) -> None:
    """Normalize GCP NAT resources."""
    if r.kind == "nat_gateway":
        for field, val in [
            ("num_vms", 1),
            ("num_nat_ips", 1),
            ("monthly_data_processed_gb", 10),
        ]:
            if field not in r.usage:
                r.usage[field] = val
                r.assumptions.append(f"Defaulted {field} to {val}.")
            else:
                try:
                    r.usage[field] = int(float(r.usage[field]))
                except ValueError, TypeError:
                    r.usage[field] = val
                    r.assumptions.append(f"Invalid {field}; defaulted to {val}.")
