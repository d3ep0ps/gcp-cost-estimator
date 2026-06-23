# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_nat(
    r: Resource, errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP NAT resources."""
    if r.kind == "nat_gateway":
        num_vms = r.usage.get("num_vms", 1)
        num_nat_ips = r.usage.get("num_nat_ips", 1)
        data = r.usage.get("monthly_data_processed_gb", 10)

        if num_vms < 1:
            errors.append("num_vms must be at least 1.")
        if num_nat_ips < 1:
            errors.append("num_nat_ips must be at least 1.")
        if data < 0:
            errors.append("monthly_data_processed_gb must be non-negative.")
        if num_vms >= 1 and num_nat_ips >= num_vms * 3:
            warnings.append("High IP-to-VM ratio configuration.")


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

    if "runtime_hours_per_month" not in r.usage:
        r.usage["runtime_hours_per_month"] = 730
        r.assumptions.append("Defaulted runtime_hours_per_month to 730.")
