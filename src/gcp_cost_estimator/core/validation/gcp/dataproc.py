# SPDX-License-Identifier: Apache-2.0

import contextlib
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.gcp.specs import resolve_machine_type_specs


def validate_dataproc(
    r: Resource, _errors: list[str], _warnings: list[str], unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Dataproc resources."""
    if r.kind == "dataproc_serverless_batch":
        unpriced.append(
            {
                "resource_id": r.resource_id,
                "reason": "Dataproc Serverless (DCU billing) not yet modelled in v1",
            }
        )


def normalize_dataproc(r: Resource) -> None:
    """Normalize GCP Dataproc resources."""
    if r.kind == "dataproc_cluster":
        if (
            "runtime_hours_per_month" not in r.usage
            or r.usage.get("runtime_hours_per_month") == 730
        ):
            if "Defaulted runtime to 730 hours/month." in r.assumptions:
                r.assumptions.remove("Defaulted runtime to 730 hours/month.")
            r.usage["runtime_hours_per_month"] = 100
            r.assumptions.append("Defaulted runtime to 100 hours/month.")

        num_m = r.attributes.get("num_master_nodes", 1)
        num_w = r.attributes.get("num_worker_nodes", 2)
        num_p = r.attributes.get("num_preemptible_nodes", 0)
        m_type = r.attributes.get("master_machine_type", "n1-standard-4")
        w_type = r.attributes.get("worker_machine_type", "n1-standard-4")

        r.attributes["num_master_nodes"] = int(num_m)
        r.attributes["num_worker_nodes"] = int(num_w)
        r.attributes["num_preemptible_nodes"] = int(num_p)
        r.attributes["master_machine_type"] = m_type
        r.attributes["worker_machine_type"] = w_type

        m_vcpus, w_vcpus = 4, 4
        with contextlib.suppress(Exception):
            m_vcpus, _ = resolve_machine_type_specs(m_type)
        with contextlib.suppress(Exception):
            w_vcpus, _ = resolve_machine_type_specs(w_type)

        if "num_master_vcpus" not in r.usage:
            r.usage["num_master_vcpus"] = m_vcpus
        if "num_worker_vcpus" not in r.usage:
            r.usage["num_worker_vcpus"] = w_vcpus
