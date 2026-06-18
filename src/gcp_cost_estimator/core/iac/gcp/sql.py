# SPDX-License-Identifier: Apache-2.0

import contextlib
from typing import Any
from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.iac.gcp.context import ParserContext


def parse_sql_database_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}

    db_ver = ctx.get("database_version")
    if db_ver:
        attributes["database_version"] = db_ver
        if ctx.is_unresolved(db_ver):
            ctx.add_assumption(f"Unresolved attribute database_version: '{db_ver}'")

    settings_list = ctx.attrs.get("settings", [])
    if isinstance(settings_list, list) and settings_list:
        settings = settings_list[0]
        if isinstance(settings, dict):
            for field in ("tier", "edition", "availability_type", "disk_type"):
                val = ctx.resolve(settings.get(field))
                if val is not None:
                    attributes[field] = val
                    if ctx.is_unresolved(val):
                        ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")

            disk_size = ctx.resolve(settings.get("disk_size"))
            if disk_size is not None:
                if ctx.is_unresolved(disk_size):
                    attributes["disk_size_gb"] = disk_size
                    ctx.add_assumption(f"Unresolved attribute disk_size: '{disk_size}'")
                else:
                    with contextlib.suppress(ValueError, TypeError):
                        attributes["disk_size_gb"] = int(disk_size)

            backup_config_list = settings.get("backup_configuration", [])
            if isinstance(backup_config_list, list) and backup_config_list:
                backup_config = backup_config_list[0]
                if isinstance(backup_config, dict):
                    backup_enabled = ctx.resolve(backup_config.get("enabled"))
                    if backup_enabled is not None:
                        attributes["backup_enabled"] = bool(backup_enabled)

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="sql",
        kind="cloud_sql_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
