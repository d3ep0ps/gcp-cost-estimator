# SPDX-License-Identifier: Apache-2.0

import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.pricing.gcp.specs import resolve_sql_tier_specs


def map_cloud_sql(
    resource: Resource, cursor: sqlite3.Cursor
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []

    region = resource.region
    tier = resource.attributes.get("tier", "")
    db_version = resource.attributes.get("database_version", "")
    edition = resource.attributes.get("edition", "ENTERPRISE").upper()
    availability_type = resource.attributes.get("availability_type", "ZONAL").upper()
    disk_type = resource.attributes.get("disk_type", "PD_SSD").upper()
    disk_size_gb = float(resource.attributes.get("disk_size_gb", 0))
    backup_enabled = bool(resource.attributes.get("backup_enabled", False))

    # 1. Resolve tier to CPU and RAM specs
    vcpu, ram_gb = resolve_sql_tier_specs(tier)
    if vcpu == 0:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"Unknown Cloud SQL tier '{tier}'",
            }
        )
        return mappings, unpriced

    # 2. Extract database family
    db_ver_upper = db_version.upper()
    if db_ver_upper.startswith("MYSQL_"):
        db_family = "mysql"
    elif db_ver_upper.startswith("POSTGRES_"):
        db_family = "postgres"
    elif db_ver_upper.startswith("SQLSERVER_"):
        db_family = "sqlserver"
    else:
        db_family = "unknown"

    # 3. Validate Edition / SQL Server combinations (ADR-010 constraint)
    if (
        edition == "ENTERPRISE_PLUS"
        and db_family == "sqlserver"
        and not db_ver_upper.endswith("_ENTERPRISE")
    ):
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (
                    "Enterprise Plus SQL Server requires an Enterprise licence "
                    f"version, got '{db_version}'"
                ),
            }
        )
        return mappings, unpriced

    # 4. Determine HA multiplier
    ha_mult = 2 if availability_type == "REGIONAL" else 1

    # 5. Look up CPU SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ?
        AND sku_group IN ('SQLGen2InstancesCPU', 'SQLInstancesCPU')
        """,
        (region,),
    )
    cpu_rows = cursor.fetchall()
    cpu_match = None

    for row in cpu_rows:
        desc = row[3].lower()
        if db_family == "sqlserver":
            family_match = "sql server" in desc or "sqlserver" in desc
        else:
            family_match = db_family in desc

        avail_match = availability_type.lower() in desc

        if edition == "ENTERPRISE_PLUS":
            ed_match = "enterprise plus" in desc or "ent plus" in desc or "entplus" in desc
        else:
            ed_match = (
                "enterprise plus" not in desc and "ent plus" not in desc and "entplus" not in desc
            )

        if family_match and avail_match and ed_match:
            cpu_match = row
            break

    if not cpu_match and cpu_rows:
        cpu_match = cpu_rows[0]

    if cpu_match:
        mappings.append(
            {
                "sku_id": cpu_match[0],
                "component": "vcpu",
                "unit": cpu_match[1],
                "unit_price": cpu_match[2],
                "qty": float(vcpu) * ha_mult * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No matching Cloud SQL CPU SKU found in region '{region}'",
            }
        )

    # 6. Look up RAM SKU
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ?
        AND sku_group IN ('SQLGen2InstancesRAM', 'SQLInstancesRAM')
        """,
        (region,),
    )
    ram_rows = cursor.fetchall()
    ram_match = None

    for row in ram_rows:
        desc = row[3].lower()
        if db_family == "sqlserver":
            family_match = "sql server" in desc or "sqlserver" in desc
        elif db_family == "postgres":
            family_match = "postgres" in desc or "postgre" in desc
        else:
            family_match = db_family in desc

        avail_match = availability_type.lower() in desc

        if edition == "ENTERPRISE_PLUS":
            ed_match = "enterprise plus" in desc or "ent plus" in desc or "entplus" in desc
        else:
            ed_match = (
                "enterprise plus" not in desc and "ent plus" not in desc and "entplus" not in desc
            )

        if family_match and avail_match and ed_match:
            ram_match = row
            break

    if not ram_match and ram_rows:
        ram_match = ram_rows[0]

    if ram_match:
        mappings.append(
            {
                "sku_id": ram_match[0],
                "component": "ram",
                "unit": ram_match[1],
                "unit_price": ram_match[2],
                "qty": float(ram_gb) * ha_mult * resource.quantity,
            }
        )
    else:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": f"No matching Cloud SQL RAM SKU found in region '{region}'",
            }
        )

    # 7. Look up Storage SKU (SSD or HDD)
    sku_group = "SSD" if disk_type == "PD_SSD" else "PDStandard"
    cursor.execute(
        """
        SELECT sku_id, unit, unit_price, description
        FROM pricing_cache
        WHERE provider = 'gcp' AND region = ? AND sku_group = ?
        """,
        (region, sku_group),
    )
    disk_rows = cursor.fetchall()
    disk_match = None

    for row in disk_rows:
        desc = row[3].lower()
        if db_family == "sqlserver":
            family_match = "sql server" in desc or "sqlserver" in desc
        else:
            family_match = db_family in desc

        if family_match:
            disk_match = row
            break

    if not disk_match and disk_rows:
        disk_match = disk_rows[0]

    if disk_match and disk_size_gb > 0:
        mappings.append(
            {
                "sku_id": disk_match[0],
                "component": "storage",
                "unit": disk_match[1],
                "unit_price": disk_match[2],
                "qty": disk_size_gb * resource.quantity,
            }
        )
    elif disk_size_gb > 0:
        unpriced.append(
            {
                "resource_id": resource.resource_id,
                "reason": (
                    f"No matching Cloud SQL storage SKU ({disk_type}) found in region '{region}'"
                ),
            }
        )

    # 8. SQL Server License SKU (if SQL Server)
    if db_family == "sqlserver":
        if "_ENTERPRISE" in db_ver_upper:
            lic_type = "enterprise"
        elif "_STANDARD" in db_ver_upper:
            lic_type = "standard"
        elif "_WEB" in db_ver_upper:
            lic_type = "web"
        else:
            lic_type = "express"

        if lic_type != "express":
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ?
                AND sku_group IN ('SQLInstancesLicense', 'SQLGen2InstancesLicense')
                """,
                (region,),
            )
            lic_rows = cursor.fetchall()

            if not lic_rows:
                cursor.execute(
                    """
                    SELECT sku_id, unit, unit_price, description
                    FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ?
                    AND (description LIKE '%license%' OR description LIKE '%licensing%')
                    """,
                    (region,),
                )
                lic_rows = cursor.fetchall()

            lic_match = None
            for row in lic_rows:
                desc = row[3].lower()
                if lic_type in desc:
                    lic_match = row
                    break

            if not lic_match and lic_rows:
                lic_match = lic_rows[0]

            if lic_match:
                mappings.append(
                    {
                        "sku_id": lic_match[0],
                        "component": "license",
                        "unit": lic_match[1],
                        "unit_price": lic_match[2],
                        "qty": float(vcpu) * ha_mult * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": (
                            f"No matching SQL Server license SKU ({lic_type}) "
                            f"found in region '{region}'"
                        ),
                    }
                )

    # 9. Backup Storage SKU (if backups enabled)
    if backup_enabled and disk_size_gb > 0:
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'Backup'
            """,
            (region,),
        )
        backup_rows = cursor.fetchall()
        backup_match = None

        for row in backup_rows:
            desc = row[3].lower()
            if db_family in desc:
                backup_match = row
                break

        if not backup_match and backup_rows:
            backup_match = backup_rows[0]

        if backup_match:
            mappings.append(
                {
                    "sku_id": backup_match[0],
                    "component": "backup",
                    "unit": backup_match[1],
                    "unit_price": backup_match[2],
                    "qty": disk_size_gb * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching Cloud SQL backup SKU found in region '{region}'",
                }
            )

    return mappings, unpriced
