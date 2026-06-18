# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_sql(
    r: Resource, errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Cloud SQL resources."""
    if r.kind == "cloud_sql_instance":
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
                    f"Resource '{r.resource_id}' has unrecognized database_version '{db_version}'."
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


def normalize_sql(r: Resource) -> None:
    """Normalize GCP Cloud SQL resources."""
    if r.kind == "cloud_sql_instance":
        if "disk_type" not in r.attributes:
            r.attributes["disk_type"] = "PD_SSD"
            r.assumptions.append("Defaulted disk_type to PD_SSD.")

        if "availability_type" not in r.attributes:
            r.attributes["availability_type"] = "ZONAL"
            r.assumptions.append("Defaulted availability_type to ZONAL.")

        if "backup_enabled" not in r.attributes:
            r.attributes["backup_enabled"] = False
            r.assumptions.append("Defaulted backup_enabled to false.")
