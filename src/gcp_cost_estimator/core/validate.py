# SPDX-License-Identifier: Apache-2.0

import re
from typing import Any

from gcp_cost_estimator.core.model import ResourceModel


def parse_k8s_quantity(val: Any, is_cpu: bool = False) -> str:
    """Parse k8s quantity string to a standardized string representation.
    
    CPU: "1000m" -> "1", "1.5" -> "1.5"
    Memory: "512Mi" -> "0.5", "1Gi" -> "1.0", "1024M" -> "1.024"
    """
    if val is None:
        return ""
    val_str = str(val).strip()
    if not val_str:
        return ""
        
    try:
        float(val_str)
        if not is_cpu:
            # If it's memory and is a whole float (like 2 or 2.0), return "2.0"
            f_val = float(val_str)
            if f_val.is_integer():
                return f"{int(f_val)}.0"
            return f"{f_val:.4f}".rstrip('0').rstrip('.')
        return val_str
    except ValueError:
        pass
        
    if is_cpu:
        if val_str.endswith("m"):
            try:
                milli = float(val_str[:-1])
                res = milli / 1000.0
                return f"{res:g}"
            except ValueError:
                return val_str
        return val_str
    else:
        m = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$", val_str)
        if not m:
            return val_str
        num_str, suffix = m.group(1), m.group(2)
        try:
            num = float(num_str)
        except ValueError:
            return val_str
            
        suffix_lower = suffix.lower()
        if suffix_lower == "ki":
            bytes_val = num * 1024
        elif suffix_lower == "mi":
            bytes_val = num * 1024 * 1024
        elif suffix_lower == "gi":
            bytes_val = num * 1024 * 1024 * 1024
        elif suffix_lower == "ti":
            bytes_val = num * 1024 * 1024 * 1024 * 1024
        elif suffix_lower == "k":
            bytes_val = num * 1000
        elif suffix_lower == "m":
            bytes_val = num * 1000 * 1000
        elif suffix_lower == "g":
            bytes_val = num * 1000 * 1000 * 1000
        elif suffix_lower == "t":
            bytes_val = num * 1000 * 1000 * 1000 * 1000
        else:
            return val_str
            
        gib = bytes_val / (1024 * 1024 * 1024)
        if gib.is_integer():
            return f"{int(gib)}.0"
        return f"{gib:.4f}".rstrip('0').rstrip('.')


def validate_resource_model(model: ResourceModel) -> dict[str, Any]:
    """Validate the canonical resource model, checking for correctness.

    Returns a dict with 'valid', 'errors', 'warnings', and optionally 'normalized_model'.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for r in model.resources:
        # Check for missing region
        if not r.region:
            warnings.append(f"Resource '{r.resource_id}' is missing region.")

        # GCP Cloud Storage bucket checks
        if r.provider == "gcp" and r.service == "storage" and r.kind == "gcs_bucket":
            sclass = r.attributes.get("storage_class")
            if sclass:
                sclass_upper = str(sclass).upper()
                if sclass_upper not in {"STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"}:
                    warnings.append(
                        f"Resource '{r.resource_id}' has unrecognized storage_class '{sclass}'."
                    )

        # GCP compute gce_instance checks
        if r.provider == "gcp" and r.service == "compute" and r.kind == "gce_instance":
            mtype = r.attributes.get("machine_type")
            if not mtype:
                errors.append(
                    f"Resource '{r.resource_id}' is a GCE instance but "
                    "has no valid machine_type attribute."
                )

        # GCP SQL cloud_sql_instance checks
        if r.provider == "gcp" and r.service == "sql" and r.kind == "cloud_sql_instance":
            tier = r.attributes.get("tier")
            if not tier:
                errors.append(
                    f"Resource '{r.resource_id}' is a Cloud SQL instance but "
                    "has no valid tier attribute."
                )

            db_version = r.attributes.get("database_version")
            if not db_version:
                errors.append(
                    f"Resource '{r.resource_id}' is a Cloud SQL instance but "
                    "has no database_version attribute."
                )
            else:
                db_ver_str = str(db_version).upper()
                if not (
                    db_ver_str.startswith("MYSQL_")
                    or db_ver_str.startswith("POSTGRES_")
                    or db_ver_str.startswith("SQLSERVER_")
                ):
                    warnings.append(
                        f"Resource '{r.resource_id}' has unrecognized "
                        f"database_version '{db_version}'."
                    )

                edition = r.attributes.get("edition", "ENTERPRISE")
                if (
                    edition == "ENTERPRISE_PLUS"
                    and db_ver_str.startswith("SQLSERVER_")
                    and not db_ver_str.endswith("_ENTERPRISE")
                ):
                    errors.append(
                        f"Resource '{r.resource_id}' specifies Enterprise Plus with SQL Server "
                        f"but has a non-Enterprise license database_version '{db_version}'. "
                        f"Enterprise Plus SQL Server requires an Enterprise SQL Server license."
                    )

            disk_size = r.attributes.get("disk_size_gb")
            if disk_size is not None:
                try:
                    if int(disk_size) < 10:
                        errors.append(
                            f"Resource '{r.resource_id}' disk size {disk_size} GB "
                            "is below GCP minimum of 10 GB."
                        )
                except ValueError, TypeError:
                    pass

            disk_type = r.attributes.get("disk_type")
            if (
                disk_type == "PD_HDD"
                and db_version
                and str(db_version).upper().startswith("SQLSERVER_")
            ):
                warnings.append(
                    f"Resource '{r.resource_id}' specifies SQL Server with HDD storage. "
                    "SQL Server does not support HDD (GCP will upgrade to SSD)."
                )

            # Enterprise Plus storage minimum 100 GB check
            edition = r.attributes.get("edition")
            if edition == "ENTERPRISE_PLUS" and disk_size is not None:
                try:
                    if int(disk_size) < 100:
                        warnings.append(
                            f"Resource '{r.resource_id}' is Enterprise Plus and "
                            f"disk size {disk_size} GB is below recommended 100 GB."
                        )
                except ValueError, TypeError:
                    pass

        if (
            r.provider == "gcp"
            and r.service == "container"
            and r.kind in {"gke_cluster", "gke_node_pool"}
        ):
            is_autopilot = r.attributes.get("enable_autopilot", False)
            if not is_autopilot:
                mtype = r.attributes.get("machine_type")
                if not mtype:
                    warnings.append(
                        f"Resource '{r.resource_id}' is missing machine_type; "
                        "defaulting to 'e2-standard-4'."
                    )

        # GCP Cloud Run checks
        if r.provider == "gcp" and r.service == "run":
            if r.kind in {"cloud_run_service", "cloud_run_job"}:
                if not r.attributes.get("cpu"):
                    errors.append(
                        f"Resource '{r.resource_id}' is a Cloud Run resource but has no CPU limit."
                    )
                if not r.attributes.get("memory"):
                    errors.append(
                        f"Resource '{r.resource_id}' is a Cloud Run resource but has no Memory limit."
                    )

        # GCP Cloud Functions checks
        if r.provider == "gcp" and r.service == "functions" and r.kind == "cloud_function":
            gen = r.attributes.get("generation", "1st_gen")
            if gen == "1st_gen":
                memory_mb_raw = r.attributes.get("available_memory_mb", 256)
                try:
                    memory_mb = int(memory_mb_raw)
                    if memory_mb not in {128, 256, 512, 1024, 2048, 4096, 8192}:
                        errors.append(
                            f"Resource '{r.resource_id}' has non-standard memory allocation '{memory_mb_raw}' for 1st-gen function."
                        )
                except (ValueError, TypeError):
                    errors.append(
                        f"Resource '{r.resource_id}' has non-standard memory allocation '{memory_mb_raw}' for 1st-gen function."
                    )
            elif gen == "2nd_gen":
                if not r.attributes.get("available_cpu"):
                    errors.append(
                        f"Resource '{r.resource_id}' is a 2nd-gen Cloud Function but has no available_cpu limit."
                    )
                if not r.attributes.get("available_memory"):
                    errors.append(
                        f"Resource '{r.resource_id}' is a 2nd-gen Cloud Function but has no available_memory limit."
                    )

        # GCP BigQuery dataset checks
        if r.provider == "gcp" and r.service == "bigquery" and r.kind == "bigquery_dataset":
            pricing_model = r.attributes.get("pricing_model")
            if pricing_model == "capacity":
                warnings.append(
                    f"Resource '{r.resource_id}' specifies capacity-based pricing, "
                    "which is not supported in v1."
                )

    normalized = None
    if not errors:
        normalized = normalize_resource_model(model)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized_model": normalized,
    }


def normalize_resource_model(model: ResourceModel) -> ResourceModel:
    """Normalize region aliases, redact secrets, and apply defaults (like 730 runtime hours)."""
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

        # 3. Apply default runtime hours if not present in usage
        if "runtime_hours_per_month" not in r.usage:
            r.usage["runtime_hours_per_month"] = 730
            assumption_msg = "Defaulted runtime to 730 hours/month."
            if assumption_msg not in r.assumptions:
                r.assumptions.append(assumption_msg)

        # 4. Apply Cloud SQL defaults
        if r.provider == "gcp" and r.service == "sql" and r.kind == "cloud_sql_instance":
            if "disk_type" not in r.attributes:
                r.attributes["disk_type"] = "PD_SSD"
                r.assumptions.append("Defaulted disk_type to PD_SSD.")

            if "availability_type" not in r.attributes:
                r.attributes["availability_type"] = "ZONAL"
                r.assumptions.append("Defaulted availability_type to ZONAL.")

            if "backup_enabled" not in r.attributes:
                r.attributes["backup_enabled"] = False
                r.assumptions.append("Defaulted backup_enabled to false.")

        # 5. Apply GCS defaults
        if r.provider == "gcp" and r.service == "storage" and r.kind == "gcs_bucket":
            sclass = r.attributes.get("storage_class")
            if sclass:
                sclass_upper = str(sclass).upper()
                if sclass_upper not in {"STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"}:
                    r.attributes["storage_class"] = "STANDARD"
                    r.assumptions.append(
                        "Defaulted storage_class to STANDARD "
                        f"(unrecognized storage_class '{sclass}' was specified)."
                    )
                else:
                    r.attributes["storage_class"] = sclass_upper
            else:
                r.attributes["storage_class"] = "STANDARD"
                r.assumptions.append(
                    "Defaulted storage_class to STANDARD. Override attributes.storage_class "
                    "(NEARLINE/COLDLINE/ARCHIVE for cold data)."
                )

            # Apply representative defaults (per defaults catalog and plan)
            if "size_gb" not in r.usage:
                r.usage["size_gb"] = 100
                r.assumptions.append(
                    "Defaulted size_gb to 100 GB. Override usage.size_gb "
                    "with your expected data volume."
                )
            else:
                try:
                    r.usage["size_gb"] = float(r.usage["size_gb"])
                except ValueError, TypeError:
                    r.usage["size_gb"] = 100
                    r.assumptions.append("Invalid size_gb specified; defaulted size_gb to 100 GB.")

            if "monthly_class_a_ops" not in r.usage:
                r.usage["monthly_class_a_ops"] = 10_000
                r.assumptions.append(
                    "Defaulted monthly_class_a_ops to 10000. Override "
                    "usage.monthly_class_a_ops (~300 writes/day assumed)."
                )
            else:
                try:
                    r.usage["monthly_class_a_ops"] = int(r.usage["monthly_class_a_ops"])
                except ValueError, TypeError:
                    r.usage["monthly_class_a_ops"] = 10_000

            if "monthly_class_b_ops" not in r.usage:
                r.usage["monthly_class_b_ops"] = 100_000
                r.assumptions.append(
                    "Defaulted monthly_class_b_ops to 100000. Override "
                    "usage.monthly_class_b_ops (~3,000 reads/day assumed)."
                )
            else:
                try:
                    r.usage["monthly_class_b_ops"] = int(r.usage["monthly_class_b_ops"])
                except ValueError, TypeError:
                    r.usage["monthly_class_b_ops"] = 100_000

            if "monthly_egress_gb" not in r.usage:
                r.usage["monthly_egress_gb"] = 10
                r.assumptions.append(
                    "Defaulted monthly_egress_gb to 10 GB. Override "
                    "usage.monthly_egress_gb with expected internet egress."
                )
            else:
                try:
                    r.usage["monthly_egress_gb"] = float(r.usage["monthly_egress_gb"])
                except ValueError, TypeError:
                    r.usage["monthly_egress_gb"] = 10

            if "monthly_retrieval_gb" not in r.usage:
                r.usage["monthly_retrieval_gb"] = 0
            else:
                try:
                    r.usage["monthly_retrieval_gb"] = float(r.usage["monthly_retrieval_gb"])
                except ValueError, TypeError:
                    r.usage["monthly_retrieval_gb"] = 0

        if (
            r.provider == "gcp"
            and r.service == "container"
            and r.kind in {"gke_cluster", "gke_node_pool"}
        ):
            is_autopilot = r.attributes.get("enable_autopilot", False)
            if not is_autopilot:
                if "node_count" not in r.attributes:
                    r.attributes["node_count"] = 3
                    r.assumptions.append("Defaulted node_count to 3.")
                else:
                    try:
                        r.attributes["node_count"] = int(r.attributes["node_count"])
                    except ValueError, TypeError:
                        r.attributes["node_count"] = 3
                        r.assumptions.append("Invalid node_count; defaulted node_count to 3.")

                if "machine_type" not in r.attributes:
                    r.attributes["machine_type"] = "e2-standard-4"
                    r.assumptions.append("Defaulted machine_type to e2-standard-4.")

                if "disk_size_gb" not in r.attributes:
                    r.attributes["disk_size_gb"] = 100
                    r.assumptions.append("Defaulted disk_size_gb to 100.")
                else:
                    try:
                        r.attributes["disk_size_gb"] = int(r.attributes["disk_size_gb"])
                    except ValueError, TypeError:
                        r.attributes["disk_size_gb"] = 100
                        r.assumptions.append("Invalid disk_size_gb; defaulted disk_size_gb to 100.")

                if "disk_type" not in r.attributes:
                    r.attributes["disk_type"] = "pd-standard"
                    r.assumptions.append("Defaulted disk_type to pd-standard.")

        # Apply BigQuery defaults
        if r.provider == "gcp" and r.service == "bigquery" and r.kind == "bigquery_dataset":
            if "active_storage_gb" not in r.usage:
                r.usage["active_storage_gb"] = 100
                r.assumptions.append(
                    "Defaulted active_storage_gb to 100 GB. Override usage.active_storage_gb "
                    "with your dataset size."
                )
            else:
                try:
                    r.usage["active_storage_gb"] = float(r.usage["active_storage_gb"])
                except ValueError, TypeError:
                    r.usage["active_storage_gb"] = 100
                    r.assumptions.append(
                        "Invalid active_storage_gb specified; "
                        "defaulted active_storage_gb to 100 GB."
                    )

            if "long_term_storage_gb" not in r.usage:
                r.usage["long_term_storage_gb"] = 0
                r.assumptions.append(
                    "Defaulted long_term_storage_gb to 0 GB. Set usage.long_term_storage_gb "
                    "for data unmodified >90 days."
                )
            else:
                try:
                    r.usage["long_term_storage_gb"] = float(r.usage["long_term_storage_gb"])
                except ValueError, TypeError:
                    r.usage["long_term_storage_gb"] = 0

            if "monthly_query_tb" not in r.usage:
                r.usage["monthly_query_tb"] = 1
                r.assumptions.append(
                    "Defaulted monthly_query_tb to 1 TB. Override usage.monthly_query_tb "
                    "with your expected query volume."
                )
            else:
                try:
                    r.usage["monthly_query_tb"] = float(r.usage["monthly_query_tb"])
                except ValueError, TypeError:
                    r.usage["monthly_query_tb"] = 1

            if "monthly_streaming_gb" not in r.usage:
                r.usage["monthly_streaming_gb"] = 0
                r.assumptions.append(
                    "Defaulted monthly_streaming_gb to 0 GB. Set usage.monthly_streaming_gb "
                    "if using the legacy Streaming API."
                )
            else:
                try:
                    r.usage["monthly_streaming_gb"] = float(r.usage["monthly_streaming_gb"])
                except ValueError, TypeError:
                    r.usage["monthly_streaming_gb"] = 0

            free_tier_assumption = (
                "Free tier (10 GB storage, 1 TB queries/month) not applied — list price only."
            )
            if free_tier_assumption not in r.assumptions:
                r.assumptions.append(free_tier_assumption)

        # Apply Cloud Run defaults & normalization
        if r.provider == "gcp" and r.service == "run":
            if r.kind == "cloud_run_service":
                if "cpu" in r.attributes:
                    r.attributes["cpu"] = parse_k8s_quantity(r.attributes["cpu"], is_cpu=True)
                if "memory" in r.attributes:
                    r.attributes["memory"] = parse_k8s_quantity(r.attributes["memory"], is_cpu=False)
                
                if "cpu_idle" not in r.attributes:
                    r.attributes["cpu_idle"] = True
                    r.assumptions.append("Defaulted cpu_idle to true.")
                else:
                    r.attributes["cpu_idle"] = str(r.attributes["cpu_idle"]).lower() in {"true", "1", "yes"}

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
                    r.usage["runtime_seconds_per_invocation"] = float(r.usage["runtime_seconds_per_invocation"])

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

        # Apply Cloud Functions defaults & normalization
        if r.provider == "gcp" and r.service == "functions" and r.kind == "cloud_function":
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
                
                ghz_map = {
                    128: 0.2,
                    256: 0.4,
                    512: 0.8,
                    1024: 1.4,
                    2048: 2.4,
                    4096: 4.8,
                    8192: 4.8
                }
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
                    r.attributes["memory"] = parse_k8s_quantity(r.attributes["available_memory"], is_cpu=False)
                
                if "cpu_idle" not in r.attributes:
                    r.attributes["cpu_idle"] = True
                else:
                    r.attributes["cpu_idle"] = str(r.attributes["cpu_idle"]).lower() in {"true", "1", "yes"}

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
                    r.usage["runtime_seconds_per_invocation"] = float(r.usage["avg_execution_time_ms"]) / 1000.0
                elif "runtime_seconds_per_invocation" not in r.usage:
                    r.usage["runtime_seconds_per_invocation"] = 0.1
                    r.assumptions.append("Defaulted runtime_seconds_per_invocation to 0.1s.")

    return model_copy
