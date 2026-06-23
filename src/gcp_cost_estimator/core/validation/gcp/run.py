# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.validation.utils import parse_k8s_quantity


def validate_run(
    r: Resource, errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Cloud Run resources."""
    if r.kind in {"cloud_run_service", "cloud_run_job"}:
        if not r.attributes.get("cpu"):
            errors.append(
                f"Resource '{r.resource_id}' is a Cloud Run resource but has no CPU limit."
            )
        if not r.attributes.get("memory"):
            errors.append(
                f"Resource '{r.resource_id}' is a Cloud Run resource but has no Memory limit."
            )


def normalize_run(r: Resource) -> None:
    """Normalize GCP Cloud Run resources."""
    if r.kind == "cloud_run_service":
        if "cpu" in r.attributes:
            r.attributes["cpu"] = parse_k8s_quantity(r.attributes["cpu"], is_cpu=True)
        if "memory" in r.attributes:
            r.attributes["memory"] = parse_k8s_quantity(r.attributes["memory"], is_cpu=False)

        if "cpu_idle" not in r.attributes:
            r.attributes["cpu_idle"] = True
            r.assumptions.append("Defaulted cpu_idle to true.")
        else:
            r.attributes["cpu_idle"] = str(r.attributes["cpu_idle"]).lower() in {
                "true",
                "1",
                "yes",
            }

        if "min_instance_count" not in r.attributes:
            r.attributes["min_instance_count"] = 0
        else:
            try:
                r.attributes["min_instance_count"] = int(r.attributes["min_instance_count"])
            except (ValueError, TypeError):
                r.attributes["min_instance_count"] = 0

        if r.attributes["min_instance_count"] > 0:
            r.assumptions.append("min_instance_count > 0 enables idle instance billing.")

        if "runtime_seconds_per_invocation" not in r.usage:
            r.usage["runtime_seconds_per_invocation"] = 1.0
            r.assumptions.append("Defaulted runtime_seconds_per_invocation to 1.0s.")
        else:
            r.usage["runtime_seconds_per_invocation"] = float(
                r.usage["runtime_seconds_per_invocation"]
            )

        if "invocations_per_month" not in r.usage:
            r.usage["invocations_per_month"] = 10_000
            r.assumptions.append("Defaulted invocations_per_month to 10000.")
        else:
            r.usage["invocations_per_month"] = int(r.usage["invocations_per_month"])

    elif r.kind == "cloud_run_job":
        if "cpu" in r.attributes:
            r.attributes["cpu"] = parse_k8s_quantity(r.attributes["cpu"], is_cpu=True)
        if "memory" in r.attributes:
            r.attributes["memory"] = parse_k8s_quantity(r.attributes["memory"], is_cpu=False)

        if "task_count" not in r.usage:
            r.usage["task_count"] = 1
            r.assumptions.append("Defaulted task_count to 1.")
        else:
            r.usage["task_count"] = int(r.usage["task_count"])

        if "runtime_seconds_per_task" not in r.usage:
            r.usage["runtime_seconds_per_task"] = 60
            r.assumptions.append("Defaulted runtime_seconds_per_task to 60s.")
        else:
            r.usage["runtime_seconds_per_task"] = int(r.usage["runtime_seconds_per_task"])

        if "executions_per_month" not in r.usage:
            r.usage["executions_per_month"] = 100
            r.assumptions.append("Defaulted executions_per_month to 100.")
        else:
            r.usage["executions_per_month"] = int(r.usage["executions_per_month"])
