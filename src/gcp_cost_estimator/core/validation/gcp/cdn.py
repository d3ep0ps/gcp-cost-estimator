# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_cdn(
    r: Resource, errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Cloud CDN resources."""
    if r.kind == "cloud_cdn_backend":
        https_frac = r.usage.get("https_fraction")
        if https_frac is not None:
            try:
                frac_val = float(https_frac)
                if not (0.0 <= frac_val <= 1.0):
                    errors.append(
                        f"Resource '{r.resource_id}' https_fraction '{https_frac}' "
                        "is out of valid range [0.0, 1.0]."
                    )
            except ValueError, TypeError:
                errors.append(
                    f"Resource '{r.resource_id}' https_fraction '{https_frac}' must be a float."
                )


def normalize_cdn(r: Resource) -> None:
    """Normalize GCP Cloud CDN resources."""
    if r.kind == "cloud_cdn_backend":
        for cdn_field, cdn_val in [
            ("monthly_cache_transfer_gb", 100.0),
            ("monthly_cache_fill_gb", 10.0),
            ("monthly_requests", 1000000.0),
            ("https_fraction", 1.0),
        ]:
            if cdn_field not in r.usage:
                r.usage[cdn_field] = cdn_val
                r.assumptions.append(f"Defaulted {cdn_field} to {cdn_val}.")
            else:
                try:
                    r.usage[cdn_field] = (
                        float(r.usage[cdn_field])
                        if cdn_field == "https_fraction"
                        else int(float(r.usage[cdn_field]))
                    )
                except ValueError, TypeError:
                    r.usage[cdn_field] = cdn_val
                    r.assumptions.append(f"Invalid {cdn_field}; defaulted to {cdn_val}.")
