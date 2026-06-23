# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.validation.utils import parse_k8s_quantity


def validate_functions(
    r: Resource, errors: list[str], _warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Cloud Functions resources."""
    if r.kind == "cloud_function":
        gen = r.attributes.get("generation", "1st_gen")
        if gen == "1st_gen":
            memory_mb_raw = r.attributes.get("available_memory_mb", 256)
            try:
                memory_mb = int(memory_mb_raw)
                if memory_mb not in {128, 256, 512, 1024, 2048, 4096, 8192}:
                    errors.append(
                        f"Resource '{r.resource_id}' has non-standard "
                        f"memory allocation '{memory_mb_raw}' for 1st-gen function."
                    )
            except (ValueError, TypeError):
                errors.append(
                    f"Resource '{r.resource_id}' has non-standard "
                    f"memory allocation '{memory_mb_raw}' for 1st-gen function."
                )
        elif gen == "2nd_gen":
            if not r.attributes.get("available_cpu"):
                errors.append(
                    f"Resource '{r.resource_id}' is a 2nd-gen Cloud Function "
                    "but has no available_cpu limit."
                )
            if not r.attributes.get("available_memory"):
                errors.append(
                    f"Resource '{r.resource_id}' is a 2nd-gen Cloud Function "
                    "but has no available_memory limit."
                )


def normalize_functions(r: Resource) -> None:
    """Normalize GCP Cloud Functions resources."""
    if r.kind == "cloud_function":
        gen = r.attributes.get("generation", "1st_gen")
        r.attributes["generation"] = gen
        if gen == "1st_gen":
            if "available_memory_mb" not in r.attributes:
                r.attributes["available_memory_mb"] = 256
            else:
                try:
                    r.attributes["available_memory_mb"] = int(r.attributes["available_memory_mb"])
                except (ValueError, TypeError):
                    r.attributes["available_memory_mb"] = 256

            memory_mb = r.attributes["available_memory_mb"]
            r.attributes["memory_gb"] = float(memory_mb) / 1024.0

            ghz_map = {128: 0.2, 256: 0.4, 512: 0.8, 1024: 1.4, 2048: 2.4, 4096: 4.8, 8192: 4.8}
            r.attributes["cpu_ghz"] = ghz_map.get(memory_mb, 0.4)

            if "min_instances" not in r.attributes:
                r.attributes["min_instances"] = 0
            else:
                try:
                    r.attributes["min_instances"] = int(r.attributes["min_instances"])
                except (ValueError, TypeError):
                    r.attributes["min_instances"] = 0

            if r.attributes["min_instances"] > 0:
                r.assumptions.append("min_instances > 0 enables idle instance billing.")

            if "invocations_per_month" not in r.usage:
                r.usage["invocations_per_month"] = 1000000
                r.assumptions.append("Defaulted invocations_per_month to 1000000.")
            else:
                r.usage["invocations_per_month"] = int(r.usage["invocations_per_month"])

            if "avg_execution_time_ms" not in r.usage:
                r.usage["avg_execution_time_ms"] = 100.0
                r.assumptions.append("Defaulted avg_execution_time_ms to 100.0ms.")
            else:
                r.usage["avg_execution_time_ms"] = float(r.usage["avg_execution_time_ms"])

        elif gen == "2nd_gen":
            if "available_cpu" in r.attributes:
                r.attributes["cpu"] = parse_k8s_quantity(r.attributes["available_cpu"], is_cpu=True)
            if "available_memory" in r.attributes:
                r.attributes["memory"] = parse_k8s_quantity(
                    r.attributes["available_memory"], is_cpu=False
                )

            if "cpu_idle" not in r.attributes:
                r.attributes["cpu_idle"] = True
            else:
                r.attributes["cpu_idle"] = str(r.attributes["cpu_idle"]).lower() in {
                    "true",
                    "1",
                    "yes",
                }

            if "min_instance_count" not in r.attributes:
                try:
                    r.attributes["min_instance_count"] = int(r.attributes.get("min_instances", 0))
                except (ValueError, TypeError):
                    r.attributes["min_instance_count"] = 0
            else:
                try:
                    r.attributes["min_instance_count"] = int(r.attributes["min_instance_count"])
                except (ValueError, TypeError):
                    r.attributes["min_instance_count"] = 0

            if r.attributes["min_instance_count"] > 0:
                r.assumptions.append("min_instance_count > 0 enables idle instance billing.")

            if "invocations_per_month" not in r.usage:
                r.usage["invocations_per_month"] = 1000000
                r.assumptions.append("Defaulted invocations_per_month to 1000000.")
            else:
                r.usage["invocations_per_month"] = int(r.usage["invocations_per_month"])

            if "avg_execution_time_ms" in r.usage:
                r.usage["runtime_seconds_per_invocation"] = (
                    float(r.usage["avg_execution_time_ms"]) / 1000.0
                )
            elif "runtime_seconds_per_invocation" not in r.usage:
                r.usage["runtime_seconds_per_invocation"] = 0.1
                r.assumptions.append("Defaulted runtime_seconds_per_invocation to 0.1s.")
