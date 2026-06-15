# SPDX-License-Identifier: Apache-2.0

import contextlib
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.gcp.specs import resolve_machine_type_specs


def validate_dataflow(
    r: Resource, errors: list[str], _warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Dataflow resources."""
    if r.kind == "dataflow_job":
        job_type = r.usage.get("job_type", "batch")
        if job_type not in {"batch", "streaming"}:
            errors.append(f"Resource '{r.resource_id}' has unrecognized job_type '{job_type}'.")

        # Unpriced check
        if r.region in ("unknown-region", "invalid-region") or not r.region:
            unpriced.append(
                {
                    "resource_id": r.resource_id,
                    "reason": (
                        f"Region '{r.region}' not supported or "
                        "missing pricing data for Dataflow"
                    ),
                }
            )


def normalize_dataflow(r: Resource) -> None:
    """Normalize GCP Dataflow resources."""
    if r.kind == "dataflow_job":
        job_type = r.usage.get("job_type", "batch")
        if job_type == "batch" and (
            "runtime_hours_per_month" not in r.usage
            or r.usage.get("runtime_hours_per_month") == 730
        ):
            if "Defaulted runtime to 730 hours/month." in r.assumptions:
                r.assumptions.remove("Defaulted runtime to 730 hours/month.")
            r.usage["runtime_hours_per_month"] = 100
            r.assumptions.append("Defaulted runtime to 100 hours/month.")

        mtype = r.attributes.get("machine_type", "n1-standard-4")

        with contextlib.suppress(Exception):
            vcpus, ram = resolve_machine_type_specs(mtype)
            r.attributes["vcpus"] = vcpus
            r.attributes["ram_gb"] = ram

        if "num_vcpus" not in r.usage:
            r.usage["num_vcpus"] = r.attributes.get("vcpus", 4)
        if "memory_gb" not in r.usage:
            r.usage["memory_gb"] = r.attributes.get("ram_gb", 15.0)

        if "max_workers" not in r.attributes:
            r.attributes["max_workers"] = 1
            r.assumptions.append("Defaulted max_workers to 1.")
        else:
            try:
                r.attributes["max_workers"] = int(r.attributes["max_workers"])
            except (ValueError, TypeError):
                r.attributes["max_workers"] = 1
                r.assumptions.append("Invalid max_workers; defaulted to 1.")

        if "job_type" not in r.usage:
            r.usage["job_type"] = "batch"
            r.assumptions.append("Defaulted job_type to batch.")
        else:
            r.usage["job_type"] = str(r.usage["job_type"]).lower()

        if "shuffle_data_gb" not in r.usage:
            r.usage["shuffle_data_gb"] = 50.0
            r.assumptions.append("Defaulted shuffle_data_gb to 50.0 GB.")
        else:
            try:
                r.usage["shuffle_data_gb"] = float(r.usage["shuffle_data_gb"])
            except (ValueError, TypeError):
                r.usage["shuffle_data_gb"] = 50.0
                r.assumptions.append("Invalid shuffle_data_gb; defaulted to 50.0 GB.")
