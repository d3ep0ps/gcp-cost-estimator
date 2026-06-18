# SPDX-License-Identifier: Apache-2.0

import re
from typing import Any

from gcp_cost_estimator.core.model import ResourceModel
from gcp_cost_estimator.core.validation.gcp import NORMALIZERS, VALIDATORS


def validate_resource_model(model: ResourceModel) -> dict[str, Any]:
    """Validate the canonical resource model, checking for correctness.

    Returns a dict with 'valid', 'errors', 'warnings', and optionally 'normalized_model'.
    """
    errors: list[str] = []
    warnings: list[str] = []
    unpriced: list[dict[str, Any]] = []

    for r in model.resources:
        # Check for missing region
        if not r.region:
            warnings.append(f"Resource '{r.resource_id}' is missing region.")

        # Delegate validation to provider-specific validation logic
        if r.provider == "gcp":
            validator = VALIDATORS.get(r.service)
            if validator:
                validator(r, errors, warnings, unpriced)

    normalized = None
    if not errors:
        normalized = normalize_resource_model(model)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized_model": normalized,
        "unpriced": unpriced,
    }


def normalize_resource_model(model: ResourceModel) -> ResourceModel:
    """Normalize region aliases, redact secrets, and apply defaults."""
    # Create a deep copy of the model
    model_copy = model.model_copy(deep=True)

    for r in model_copy.resources:
        # 1. Normalize region alias (e.g. us-central-1 -> us-central1)
        if r.region:
            r.region = re.sub(r"-(\d+)$", r"\1", r.region.strip()).lower()

        # 2. Redact sensitive attributes (secret, password)
        for k in list(r.attributes.keys()):
            if "secret" in k.lower() or "password" in k.lower():
                r.attributes[k] = "[REDACTED]"
            elif isinstance(r.attributes[k], dict):
                for sub_k in list(r.attributes[k].keys()):
                    if "secret" in sub_k.lower() or "password" in sub_k.lower():
                        r.attributes[k][sub_k] = "[REDACTED]"

        # 3. Apply default runtime hours if not present in usage
        if "runtime_hours_per_month" not in r.usage:
            r.usage["runtime_hours_per_month"] = 730
            assumption_msg = "Defaulted runtime to 730 hours/month."
            if assumption_msg not in r.assumptions:
                r.assumptions.append(assumption_msg)

        # 4. Delegate normalization to provider-specific normalization logic
        if r.provider == "gcp":
            normalizer = NORMALIZERS.get(r.service)
            if normalizer:
                normalizer(r)

    # 5. Cross-resource propagation: Propagate AlloyDB cluster location to instances if missing
    _propagate_alloydb_regions(model_copy)

    return model_copy


def _propagate_alloydb_regions(model: ResourceModel) -> None:
    """Propagate AlloyDB cluster regions to child instances if missing."""
    alloydb_cluster_regions = {}
    for res in model.resources:
        if res.provider == "gcp" and res.service == "alloydb" and res.kind == "alloydb_cluster":
            clean_id = res.resource_id.split(".")[-1]
            if res.region:
                alloydb_cluster_regions[clean_id] = res.region
                alloydb_cluster_regions[res.resource_id] = res.region

    for res in model.resources:
        is_alloy_inst = (
            res.provider == "gcp" and res.service == "alloydb" and res.kind == "alloydb_instance"
        )
        if is_alloy_inst and not res.region:
            cluster_ref = res.attributes.get("cluster_ref")
            if cluster_ref:
                clean_ref = str(cluster_ref).split(".")[-1]
                if clean_ref in alloydb_cluster_regions:
                    res.region = alloydb_cluster_regions[clean_ref]
                    msg = f"Derived region '{res.region}' from parent cluster."
                    res.assumptions.append(msg)
                elif str(cluster_ref) in alloydb_cluster_regions:
                    res.region = alloydb_cluster_regions[str(cluster_ref)]
                    msg = f"Derived region '{res.region}' from parent cluster."
                    res.assumptions.append(msg)
