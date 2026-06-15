# SPDX-License-Identifier: Apache-2.0

import contextlib
import re
from typing import Any

from gcp_cost_estimator.core.model import AttachedResource, ResourceModel


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
            return f"{f_val:.4f}".rstrip("0").rstrip(".")
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
    return f"{gib:.4f}".rstrip("0").rstrip(".")


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
        if (
            r.provider == "gcp"
            and r.service == "run"
            and r.kind in {"cloud_run_service", "cloud_run_job"}
        ):
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
                            f"Resource '{r.resource_id}' has non-standard "
                            f"memory allocation '{memory_mb_raw}' for 1st-gen function."
                        )
                except ValueError, TypeError:
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

        # GCP App Engine checks
        if r.provider == "gcp" and r.service == "appengine":
            if r.kind == "app_engine_standard_version":
                iclass = r.attributes.get("instance_class", "F1")
                if iclass not in {"F1", "F2", "F4", "F4_1G", "B1", "B2", "B4", "B4_1G", "B8"}:
                    errors.append(
                        f"Resource '{r.resource_id}' has non-standard "
                        f"instance class '{iclass}' for App Engine standard."
                    )
            elif r.kind == "app_engine_flexible_version":
                for field in ("cpu", "memory_gb", "disk_gb"):
                    if field in r.attributes:
                        try:
                            float(r.attributes[field])
                        except ValueError, TypeError:
                            errors.append(
                                f"Resource '{r.resource_id}' has invalid '{field}' attribute."
                            )

        # GCP BigQuery dataset checks
        if r.provider == "gcp" and r.service == "bigquery" and r.kind == "bigquery_dataset":
            pricing_model = r.attributes.get("pricing_model")
            if pricing_model == "capacity":
                warnings.append(
                    f"Resource '{r.resource_id}' specifies capacity-based pricing, "
                    "which is not supported in v1."
                )

        # GCP Spanner instance checks
        if r.provider == "gcp" and r.service == "spanner" and r.kind == "spanner_instance":
            edition = r.attributes.get("edition", "STANDARD")
            if edition not in {"STANDARD", "ENTERPRISE", "ENTERPRISE_PLUS"}:
                warnings.append(f"Resource '{r.resource_id}' has unrecognized edition '{edition}'.")
            config = r.attributes.get("config")
            if not config:
                warnings.append(f"Resource '{r.resource_id}' is missing config.")
            num_nodes = r.attributes.get("num_nodes")
            processing_units = r.attributes.get("processing_units")
            if num_nodes is not None and processing_units is not None:
                msg = (
                    f"Resource '{r.resource_id}' cannot specify both "
                    "num_nodes and processing_units."
                )
                errors.append(msg)

        # GCP Firestore database checks
        if r.provider == "gcp" and r.service == "firestore" and r.kind == "firestore_database":
            db_type = r.attributes.get("database_type", "FIRESTORE_NATIVE")
            if db_type not in {"FIRESTORE_NATIVE", "DATASTORE_MODE"}:
                warnings.append(
                    f"Resource '{r.resource_id}' has unrecognized database_type '{db_type}'."
                )

        # GCP Memorystore checks
        if r.provider == "gcp" and r.service == "memorystore":
            if r.kind == "redis_instance":
                if "memory_size_gb" not in r.attributes:
                    errors.append(
                        f"Resource '{r.resource_id}' is missing memory_size_gb attribute."
                    )
            elif r.kind == "memorystore_instance":
                node_type = r.attributes.get("node_type")
                valid_types = {
                    "SHARED_CORE_NANO",
                    "STANDARD_SMALL",
                    "HIGHMEM_MEDIUM",
                    "HIGHMEM_XLARGE",
                }
                if node_type and node_type not in valid_types:
                    warnings.append(
                        f"Resource '{r.resource_id}' has unrecognized node_type '{node_type}'."
                    )

        # GCP Bigtable checks
        if r.provider == "gcp" and r.service == "bigtable" and r.kind == "bigtable_instance":
            inst_type = r.attributes.get("instance_type", "PRODUCTION").upper()
            clusters = r.attributes.get("clusters")
            if not clusters:
                errors.append(f"Resource '{r.resource_id}' is missing cluster configuration.")
            else:
                for cl in clusters:
                    if not cl.get("zone"):
                        errors.append(f"Resource '{r.resource_id}' cluster is missing zone.")

                    num_nodes = cl.get("num_nodes")
                    if inst_type == "DEVELOPMENT":
                        if num_nodes is not None:
                            try:
                                if int(num_nodes) != 1:
                                    msg = (
                                        f"Resource '{r.resource_id}' is a "
                                        "DEVELOPMENT instance but num_nodes is not 1."
                                    )
                                    errors.append(msg)
                            except ValueError, TypeError:
                                msg = (
                                    f"Resource '{r.resource_id}' is a "
                                    "DEVELOPMENT instance but num_nodes is not 1."
                                )
                                errors.append(msg)
                    elif inst_type == "PRODUCTION" and num_nodes is not None:
                        try:
                            if int(num_nodes) < 3:
                                msg = (
                                    f"Resource '{r.resource_id}' cluster has "
                                    "fewer than 3 nodes (recommended minimum for production)."
                                )
                                warnings.append(msg)
                        except ValueError, TypeError:
                            pass

        # GCP AlloyDB checks
        if r.provider == "gcp" and r.service == "alloydb" and r.kind == "alloydb_instance":
            if "cpu_count" not in r.attributes:
                errors.append(f"Resource '{r.resource_id}' is missing cpu_count attribute.")
            else:
                cpu_count = r.attributes.get("cpu_count")
                if cpu_count is None:
                    errors.append(f"Resource '{r.resource_id}' cpu_count cannot be null.")
                else:
                    try:
                        cpu_val = int(cpu_count)
                        if cpu_val not in {2, 4, 8, 16, 32, 64, 96, 128}:
                            msg = (
                                f"Resource '{r.resource_id}' has "
                                f"unsupported vcpu count '{cpu_val}'."
                            )
                            warnings.append(msg)
                    except ValueError, TypeError:
                        errors.append(f"Resource '{r.resource_id}' cpu_count must be an integer.")

        # GCP Cloud CDN checks
        if r.provider == "gcp" and r.service == "cdn" and r.kind == "cloud_cdn_backend":
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

        # GCP Dataflow checks
        if r.provider == "gcp" and r.service == "dataflow" and r.kind == "dataflow_job":
            job_type = r.usage.get("job_type", "batch")
            if job_type not in {"batch", "streaming"}:
                errors.append(f"Resource '{r.resource_id}' has unrecognized job_type '{job_type}'.")

    normalized = None
    if not errors:
        normalized = normalize_resource_model(model)

    unpriced: list[dict[str, Any]] = []
    for r in model.resources:
        if r.provider == "gcp" and r.service == "pubsub" and "lite" in str(r.kind).lower():
            unpriced.append(
                {
                    "resource_id": r.resource_id,
                    "reason": "Pub/Sub Lite was deprecated on 2026-03-18",
                }
            )
        if (
            r.provider == "gcp"
            and r.service == "dataflow"
            and r.kind == "dataflow_job"
            and (r.region in ("unknown-region", "invalid-region") or not r.region)
        ):
            unpriced.append(
                {
                    "resource_id": r.resource_id,
                    "reason": (
                        f"Region '{r.region}' not supported or "
                        "missing pricing data for Dataflow"
                    ),
                }
            )
        if (
            r.provider == "gcp"
            and r.service == "dataproc"
            and r.kind == "dataproc_serverless_batch"
        ):
            unpriced.append(
                {
                    "resource_id": r.resource_id,
                    "reason": "Dataproc Serverless (DCU billing) not yet modelled in v1",
                }
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized_model": normalized,
        "unpriced": unpriced,
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
                    r.attributes["memory"] = parse_k8s_quantity(
                        r.attributes["memory"], is_cpu=False
                    )

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
                    except ValueError, TypeError:
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
                    r.attributes["memory"] = parse_k8s_quantity(
                        r.attributes["memory"], is_cpu=False
                    )

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
                        r.attributes["available_memory_mb"] = int(
                            r.attributes["available_memory_mb"]
                        )
                    except ValueError, TypeError:
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
                    except ValueError, TypeError:
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
                    r.attributes["cpu"] = parse_k8s_quantity(
                        r.attributes["available_cpu"], is_cpu=True
                    )
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
                        r.attributes["min_instance_count"] = int(
                            r.attributes.get("min_instances", 0)
                        )
                    except ValueError, TypeError:
                        r.attributes["min_instance_count"] = 0
                else:
                    try:
                        r.attributes["min_instance_count"] = int(r.attributes["min_instance_count"])
                    except ValueError, TypeError:
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

        # Apply App Engine defaults & normalization
        if r.provider == "gcp" and r.service == "appengine":
            if r.kind == "app_engine_standard_version":
                if "instance_class" not in r.attributes:
                    r.attributes["instance_class"] = "F1"
                    r.assumptions.append("Defaulted instance_class to F1.")
                else:
                    r.attributes["instance_class"] = str(r.attributes["instance_class"]).upper()

                free_tier_msg = (
                    "App Engine standard includes a daily free tier per project "
                    "(e.g. 28 hours for F-classes, 9 hours for B-classes) — "
                    "not applied (list price only)."
                )
                if free_tier_msg not in r.assumptions:
                    r.assumptions.append(free_tier_msg)

            elif r.kind == "app_engine_flexible_version":
                if "cpu" not in r.attributes:
                    r.attributes["cpu"] = 1
                else:
                    try:
                        r.attributes["cpu"] = int(r.attributes["cpu"])
                    except ValueError, TypeError:
                        r.attributes["cpu"] = 1

                if "memory_gb" not in r.attributes:
                    r.attributes["memory_gb"] = 3.75
                else:
                    try:
                        r.attributes["memory_gb"] = float(r.attributes["memory_gb"])
                    except ValueError, TypeError:
                        r.attributes["memory_gb"] = 3.75

                if "disk_gb" not in r.attributes:
                    disk_gb = 10
                    r.attributes["disk_gb"] = disk_gb
                else:
                    try:
                        disk_gb = int(r.attributes["disk_gb"])
                        r.attributes["disk_gb"] = disk_gb
                    except ValueError, TypeError:
                        disk_gb = 10
                        r.attributes["disk_gb"] = disk_gb

                if not any(a.kind == "pd_persistent_disk" for a in r.attached):
                    r.attached.append(
                        AttachedResource(
                            kind="pd_persistent_disk", quantity=1, attributes={"size_gb": disk_gb}
                        )
                    )

        # Apply Spanner defaults
        if r.provider == "gcp" and r.service == "spanner" and r.kind == "spanner_instance":
            edition = r.attributes.get("edition")
            if edition:
                edition_upper = str(edition).upper()
                if edition_upper not in {"STANDARD", "ENTERPRISE", "ENTERPRISE_PLUS"}:
                    r.attributes["edition"] = "STANDARD"
                    msg = (
                        "Defaulted edition to STANDARD "
                        f"(unrecognized edition '{edition}' was specified)."
                    )
                    r.assumptions.append(msg)
                else:
                    r.attributes["edition"] = edition_upper
            else:
                r.attributes["edition"] = "STANDARD"
                r.assumptions.append("Defaulted edition to STANDARD.")

            num_nodes = r.attributes.get("num_nodes")
            processing_units = r.attributes.get("processing_units")

            if num_nodes is not None and processing_units is not None:
                pass
            elif num_nodes is not None:
                try:
                    r.attributes["processing_units"] = int(num_nodes) * 1000
                    msg = (
                        f"Converted num_nodes={num_nodes} to "
                        f"processing_units={r.attributes['processing_units']}."
                    )
                    r.assumptions.append(msg)
                except ValueError, TypeError:
                    r.attributes["processing_units"] = 100
                    r.assumptions.append("Invalid num_nodes; defaulted processing_units to 100.")
            elif processing_units is not None:
                try:
                    r.attributes["processing_units"] = int(processing_units)
                except ValueError, TypeError:
                    r.attributes["processing_units"] = 100
                    msg = "Invalid processing_units; defaulted processing_units to 100."
                    r.assumptions.append(msg)
            else:
                r.attributes["processing_units"] = 100
                r.assumptions.append("Defaulted processing_units to 100.")

            if "storage_gb" not in r.usage:
                r.usage["storage_gb"] = 0
                r.assumptions.append("Defaulted storage_gb to 0 GB.")
            else:
                try:
                    r.usage["storage_gb"] = float(r.usage["storage_gb"])
                except ValueError, TypeError:
                    r.usage["storage_gb"] = 0
                    r.assumptions.append("Invalid storage_gb; defaulted storage_gb to 0 GB.")

            config = r.attributes.get("config")
            if config:
                config_str = str(config).lower()
                if config_str.startswith("regional-"):
                    config_type = "regional"
                    mult = 1
                elif config_str in {"nam4", "eur4"}:
                    config_type = "dual-region"
                    mult = 2
                else:
                    config_type = "multi-region"
                    mult = 3
                r.attributes["config_type"] = config_type
                msg = f"Derived config_type={config_type} with storage multiplier {mult}x."
                r.assumptions.append(msg)

        # Apply Firestore defaults
        if r.provider == "gcp" and r.service == "firestore" and r.kind == "firestore_database":
            db_type = r.attributes.get("database_type")
            if db_type:
                db_type_upper = str(db_type).upper()
                if db_type_upper not in {"FIRESTORE_NATIVE", "DATASTORE_MODE"}:
                    r.attributes["database_type"] = "FIRESTORE_NATIVE"
                    msg = (
                        "Defaulted database_type to FIRESTORE_NATIVE "
                        f"(unrecognized database_type '{db_type}' was specified)."
                    )
                    r.assumptions.append(msg)
                else:
                    r.attributes["database_type"] = db_type_upper
            else:
                r.attributes["database_type"] = "FIRESTORE_NATIVE"
                r.assumptions.append("Defaulted database_type to FIRESTORE_NATIVE.")

            # Normalise Firestore location IDs to GCP regions
            if r.region:
                location_map = {
                    "us-central": "us-central1",
                    "europe-west": "europe-west1",
                    "asia-northeast": "asia-northeast1",
                }
                r.region = location_map.get(r.region.lower(), r.region)

            # Usage defaults
            for field, val in [
                ("storage_gb", 1),
                ("monthly_reads", 500000),
                ("monthly_writes", 100000),
                ("monthly_deletes", 10000),
                ("monthly_egress_gb", 0),
            ]:
                if field not in r.usage:
                    r.usage[field] = val
                    r.assumptions.append(f"Defaulted {field} to {val}.")
                else:
                    try:
                        is_float = field in ("storage_gb", "monthly_egress_gb")
                        r.usage[field] = float(r.usage[field]) if is_float else int(r.usage[field])
                    except ValueError, TypeError:
                        r.usage[field] = val
                        r.assumptions.append(f"Invalid {field}; defaulted to {val}.")

            r.assumptions.append(
                "Free tier (1 GB storage, 50K reads/day, 20K writes/day, "
                "20K deletes/day) not applied — list price only."
            )

        # Apply Memorystore defaults
        if r.provider == "gcp" and r.service == "memorystore":
            if r.kind == "redis_instance":
                if "tier" not in r.attributes:
                    r.attributes["tier"] = "BASIC"
                    r.assumptions.append("Defaulted tier to BASIC.")
                else:
                    tier_val = str(r.attributes["tier"]).upper()
                    if tier_val not in {"BASIC", "STANDARD_HA"}:
                        r.attributes["tier"] = "BASIC"
                        msg = (
                            "Defaulted tier to BASIC "
                            f"(unrecognized tier '{tier_val}' was specified)."
                        )
                        r.assumptions.append(msg)
                    else:
                        r.attributes["tier"] = tier_val

                if "memory_size_gb" in r.attributes:
                    with contextlib.suppress(ValueError, TypeError):
                        r.attributes["memory_size_gb"] = float(r.attributes["memory_size_gb"])

            elif r.kind == "memorystore_instance":
                if "shard_count" not in r.attributes:
                    r.attributes["shard_count"] = 1
                    r.assumptions.append("Defaulted shard_count to 1.")
                else:
                    try:
                        r.attributes["shard_count"] = int(r.attributes["shard_count"])
                    except ValueError, TypeError:
                        r.attributes["shard_count"] = 1
                        r.assumptions.append("Invalid shard_count; defaulted to 1.")

                if "mode" not in r.attributes:
                    r.attributes["mode"] = "STANDALONE"
                    r.assumptions.append("Defaulted mode to STANDALONE.")
                else:
                    mode_val = str(r.attributes["mode"]).upper()
                    if mode_val not in {"STANDALONE", "CLUSTER"}:
                        r.attributes["mode"] = "STANDALONE"
                        msg = (
                            "Defaulted mode to STANDALONE "
                            f"(unrecognized mode '{mode_val}' was specified)."
                        )
                        r.assumptions.append(msg)
                    else:
                        r.attributes["mode"] = mode_val

        # Apply Bigtable defaults
        if r.provider == "gcp" and r.service == "bigtable" and r.kind == "bigtable_instance":
            if "instance_type" not in r.attributes:
                r.attributes["instance_type"] = "PRODUCTION"
                r.assumptions.append("Defaulted instance_type to PRODUCTION.")
            else:
                inst_type = str(r.attributes["instance_type"]).upper()
                if inst_type not in {"PRODUCTION", "DEVELOPMENT"}:
                    r.attributes["instance_type"] = "PRODUCTION"
                    msg = (
                        "Defaulted instance_type to PRODUCTION "
                        f"(unrecognized instance_type '{inst_type}' was specified)."
                    )
                    r.assumptions.append(msg)
                else:
                    r.attributes["instance_type"] = inst_type

            # Cluster defaults & region derivation
            clusters = r.attributes.get("clusters")
            if clusters:
                for cl in clusters:
                    # Default storage_type to SSD
                    if "storage_type" not in cl:
                        cl["storage_type"] = "SSD"
                        r.assumptions.append("Defaulted storage_type to SSD.")
                    else:
                        stype = str(cl["storage_type"]).upper()
                        if stype not in {"SSD", "HDD"}:
                            cl["storage_type"] = "SSD"
                            msg = (
                                "Defaulted storage_type to SSD "
                                f"(unrecognized storage_type '{stype}' was specified)."
                            )
                            r.assumptions.append(msg)
                        else:
                            cl["storage_type"] = stype

                    # Default num_nodes
                    if "num_nodes" not in cl:
                        if r.attributes["instance_type"] == "DEVELOPMENT":
                            cl["num_nodes"] = 1
                            msg = "Defaulted num_nodes to 1 for DEVELOPMENT instance."
                            r.assumptions.append(msg)
                        else:
                            cl["num_nodes"] = 3
                            r.assumptions.append("Defaulted num_nodes to 3.")
                    else:
                        try:
                            cl["num_nodes"] = int(cl["num_nodes"])
                        except ValueError, TypeError:
                            is_dev = r.attributes["instance_type"] == "DEVELOPMENT"
                            cl["num_nodes"] = 1 if is_dev else 3

                    # Derive region from zone (strip trailing zone letter like -a, -b, -c)
                    zone = cl.get("zone")
                    if zone:
                        reg = re.sub(r"-[a-z]$", "", str(zone).strip()).lower()
                        cl["region"] = reg

            if "storage_gb_per_cluster" not in r.usage:
                r.usage["storage_gb_per_cluster"] = 0
                r.assumptions.append("Defaulted storage_gb_per_cluster to 0.")
            else:
                try:
                    r.usage["storage_gb_per_cluster"] = float(r.usage["storage_gb_per_cluster"])
                except ValueError, TypeError:
                    r.usage["storage_gb_per_cluster"] = 0
                    r.assumptions.append("Invalid storage_gb_per_cluster; defaulted to 0.")

        # Apply AlloyDB defaults
        if r.provider == "gcp" and r.service == "alloydb":
            if r.kind == "alloydb_cluster":
                if "storage_gb" not in r.usage:
                    r.usage["storage_gb"] = 100
                    r.assumptions.append("Defaulted storage_gb to 100.")
                else:
                    try:
                        r.usage["storage_gb"] = float(r.usage["storage_gb"])
                    except ValueError, TypeError:
                        r.usage["storage_gb"] = 100
                        r.assumptions.append("Invalid storage_gb; defaulted to 100.")

                if "backup_enabled" not in r.usage:
                    r.usage["backup_enabled"] = False
                    r.assumptions.append("Defaulted backup_enabled to False.")
                else:
                    if isinstance(r.usage["backup_enabled"], str):
                        r.usage["backup_enabled"] = r.usage["backup_enabled"].lower() == "true"
                    else:
                        r.usage["backup_enabled"] = bool(r.usage["backup_enabled"])

            elif r.kind == "alloydb_instance":
                if "instance_type" not in r.attributes:
                    r.attributes["instance_type"] = "PRIMARY"
                    r.assumptions.append("Defaulted instance_type to PRIMARY.")
                else:
                    itype = str(r.attributes["instance_type"]).upper()
                    if itype not in {"PRIMARY", "READ_POOL"}:
                        r.attributes["instance_type"] = "PRIMARY"
                        msg = (
                            "Defaulted instance_type to PRIMARY "
                            f"(unrecognized instance_type '{itype}' was specified)."
                        )
                        r.assumptions.append(msg)
                    else:
                        r.attributes["instance_type"] = itype

                if r.attributes["instance_type"] == "READ_POOL":
                    if "node_count" not in r.attributes:
                        r.attributes["node_count"] = 1
                        r.assumptions.append("Defaulted node_count to 1 for READ_POOL instance.")
                    else:
                        try:
                            r.attributes["node_count"] = int(r.attributes["node_count"])
                        except ValueError, TypeError:
                            r.attributes["node_count"] = 1
                            r.assumptions.append("Invalid node_count; defaulted to 1.")

        # Apply CDN defaults
        if r.provider == "gcp" and r.service == "cdn" and r.kind == "cloud_cdn_backend":
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

        # Apply DNS defaults
        if r.provider == "gcp" and r.service == "dns" and r.kind == "dns_managed_zone":
            if "visibility" not in r.attributes:
                r.attributes["visibility"] = "public"
                r.assumptions.append("Defaulted visibility to public.")
            else:
                r.attributes["visibility"] = str(r.attributes["visibility"]).lower()

            if "monthly_queries" not in r.usage:
                r.usage["monthly_queries"] = 1000000
                r.assumptions.append("Defaulted monthly_queries to 1000000.")
            else:
                try:
                    r.usage["monthly_queries"] = int(float(r.usage["monthly_queries"]))
                except ValueError, TypeError:
                    r.usage["monthly_queries"] = 1000000
                    r.assumptions.append("Invalid monthly_queries; defaulted to 1000000.")

        # Apply NAT defaults
        if r.provider == "gcp" and r.service == "nat" and r.kind == "nat_gateway":
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

        # Apply VPC defaults
        if r.provider == "gcp" and r.service == "vpc" and r.kind == "compute_address":
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

        # Apply Cloud Armor defaults
        if r.provider == "gcp" and r.service == "armor" and r.kind == "compute_security_policy":
            if "rule_count" not in r.attributes:
                r.attributes["rule_count"] = 0
            else:
                try:
                    r.attributes["rule_count"] = int(r.attributes["rule_count"])
                except ValueError, TypeError:
                    r.attributes["rule_count"] = 0

            if "monthly_requests" not in r.usage:
                r.usage["monthly_requests"] = 1000000
                r.assumptions.append("Defaulted monthly_requests to 1000000.")
            else:
                try:
                    r.usage["monthly_requests"] = int(float(r.usage["monthly_requests"]))
                except ValueError, TypeError:
                    r.usage["monthly_requests"] = 1000000
                    r.assumptions.append("Invalid monthly_requests; defaulted to 1000000.")

        # Apply Pub/Sub defaults
        if r.provider == "gcp" and r.service == "pubsub":
            if r.kind == "pubsub_topic":
                if "monthly_message_throughput_gb" not in r.usage:
                    r.usage["monthly_message_throughput_gb"] = 10.0
                    r.assumptions.append("Defaulted monthly_message_throughput_gb to 10.0 GB.")
                else:
                    try:
                        r.usage["monthly_message_throughput_gb"] = float(
                            r.usage["monthly_message_throughput_gb"]
                        )
                    except ValueError, TypeError:
                        r.usage["monthly_message_throughput_gb"] = 10.0
                        r.assumptions.append(
                            "Invalid monthly_message_throughput_gb; defaulted to 10.0 GB."
                        )
                r.assumptions.append("First 10 GiB/month free is not applied.")
            elif r.kind == "pubsub_subscription":
                if "retain_acked_messages" not in r.attributes:
                    r.attributes["retain_acked_messages"] = False
                else:
                    if isinstance(r.attributes["retain_acked_messages"], str):
                        r.attributes["retain_acked_messages"] = r.attributes[
                            "retain_acked_messages"
                        ].lower() in {"true", "1", "yes"}
                    else:
                        r.attributes["retain_acked_messages"] = bool(
                            r.attributes["retain_acked_messages"]
                        )

                if "subscription_storage_gb" not in r.usage:
                    r.usage["subscription_storage_gb"] = 0.0
                    r.assumptions.append("Defaulted subscription_storage_gb to 0.0 GB.")
                else:
                    try:
                        r.usage["subscription_storage_gb"] = float(
                            r.usage["subscription_storage_gb"]
                        )
                    except ValueError, TypeError:
                        r.usage["subscription_storage_gb"] = 0.0
                        r.assumptions.append(
                            "Invalid subscription_storage_gb; defaulted to 0.0 GB."
                        )

        # Apply Dataflow defaults
        if r.provider == "gcp" and r.service == "dataflow" and r.kind == "dataflow_job":
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
            from gcp_cost_estimator.core.pricing.gcp.specs import resolve_machine_type_specs

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
                except ValueError, TypeError:
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
                except ValueError, TypeError:
                    r.usage["shuffle_data_gb"] = 50.0
                    r.assumptions.append("Invalid shuffle_data_gb; defaulted to 50.0 GB.")

        # Apply Dataproc defaults
        if r.provider == "gcp" and r.service == "dataproc" and r.kind == "dataproc_cluster":
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

            from gcp_cost_estimator.core.pricing.gcp.specs import resolve_machine_type_specs

            m_vcpus, w_vcpus = 4, 4
            with contextlib.suppress(Exception):
                m_vcpus, _ = resolve_machine_type_specs(m_type)
            with contextlib.suppress(Exception):
                w_vcpus, _ = resolve_machine_type_specs(w_type)

            if "num_master_vcpus" not in r.usage:
                r.usage["num_master_vcpus"] = m_vcpus
            if "num_worker_vcpus" not in r.usage:
                r.usage["num_worker_vcpus"] = w_vcpus

        # Propagate AlloyDB cluster location to instances if missing
        alloydb_cluster_regions = {}
        for res in model_copy.resources:
            if res.provider == "gcp" and res.service == "alloydb" and res.kind == "alloydb_cluster":
                clean_id = res.resource_id.split(".")[-1]
                if res.region:
                    alloydb_cluster_regions[clean_id] = res.region
                    alloydb_cluster_regions[res.resource_id] = res.region

        for res in model_copy.resources:
            is_alloy_inst = (
                res.provider == "gcp"
                and res.service == "alloydb"
                and res.kind == "alloydb_instance"
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

    return model_copy
