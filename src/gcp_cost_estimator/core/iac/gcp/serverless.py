# SPDX-License-Identifier: Apache-2.0

import contextlib
from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def parse_cloud_run_service(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    template_list = ctx.attrs.get("template", [])
    if not isinstance(template_list, list):
        template_list = [template_list]
    for template in template_list:
        if not isinstance(template, dict):
            continue
        scaling_list = template.get("scaling", [])
        if not isinstance(scaling_list, list):
            scaling_list = [scaling_list]
        for scaling in scaling_list:
            if not isinstance(scaling, dict):
                continue
            for field in ("min_instance_count", "max_instance_count"):
                val = ctx.resolve(scaling.get(field))
                if val is not None:
                    if ctx.is_unresolved(val):
                        ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")
                    else:
                        with contextlib.suppress(ValueError, TypeError):
                            attributes[field] = int(val)
        containers_list = template.get("containers", [])
        if not isinstance(containers_list, list):
            containers_list = [containers_list]
        for container in containers_list:
            if not isinstance(container, dict):
                continue
            resources_list = container.get("resources", [])
            if not isinstance(resources_list, list):
                resources_list = [resources_list]
            for res_conf in resources_list:
                if not isinstance(res_conf, dict):
                    continue
                cpu_idle_val = ctx.resolve(res_conf.get("cpu_idle"))
                if cpu_idle_val is not None:
                    if ctx.is_unresolved(cpu_idle_val):
                        ctx.add_assumption(f"Unresolved attribute cpu_idle: '{cpu_idle_val}'")
                    else:
                        attributes["cpu_idle"] = str(cpu_idle_val).lower() in {"true", "1", "yes"}
                limits_list = res_conf.get("limits", [])
                if not isinstance(limits_list, list):
                    limits_list = [limits_list]
                for limits in limits_list:
                    if not isinstance(limits, dict):
                        continue
                    for limit_key in ("cpu", "memory"):
                        val = ctx.resolve(limits.get(limit_key))
                        if val is not None:
                            attributes[limit_key] = val
                            if ctx.is_unresolved(val):
                                ctx.add_assumption(f"Unresolved attribute {limit_key}: '{val}'")

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="run",
        kind="cloud_run_service",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_cloud_run_job(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    template_list = ctx.attrs.get("template", [])
    if not isinstance(template_list, list):
        template_list = [template_list]
    for template in template_list:
        if not isinstance(template, dict):
            continue
        sub_template_list = template.get("template", [])
        if not isinstance(sub_template_list, list):
            sub_template_list = [sub_template_list]
        for sub_template in sub_template_list:
            if not isinstance(sub_template, dict):
                continue
            containers_list = sub_template.get("containers", [])
            if not isinstance(containers_list, list):
                containers_list = [containers_list]
            for container in containers_list:
                if not isinstance(container, dict):
                    continue
                resources_list = container.get("resources", [])
                if not isinstance(resources_list, list):
                    resources_list = [resources_list]
                for res_conf in resources_list:
                    if not isinstance(res_conf, dict):
                        continue
                    limits_list = res_conf.get("limits", [])
                    if not isinstance(limits_list, list):
                        limits_list = [limits_list]
                    for limits in limits_list:
                        if not isinstance(limits, dict):
                            continue
                        for limit_key in ("cpu", "memory"):
                            val = ctx.resolve(limits.get(limit_key))
                            if val is not None:
                                attributes[limit_key] = val
                                if ctx.is_unresolved(val):
                                    ctx.add_assumption(f"Unresolved attribute {limit_key}: '{val}'")

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="run",
        kind="cloud_run_job",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_cloudfunctions_function(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {"generation": "1st_gen"}
    for field in ("available_memory_mb", "min_instances"):
        val = ctx.get(field)
        if val is not None:
            attributes[field] = val
            if ctx.is_unresolved(val):
                ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="functions",
        kind="cloud_function",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_cloudfunctions2_function(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {"generation": "2nd_gen"}
    sc_list = ctx.attrs.get("service_config", [])
    if not isinstance(sc_list, list):
        sc_list = [sc_list]
    for sc in sc_list:
        if not isinstance(sc, dict):
            continue
        for field in (
            "available_memory",
            "available_cpu",
            "min_instance_count",
            "max_instance_count",
        ):
            val = ctx.resolve(sc.get(field))
            if val is not None:
                attributes[field] = val
                if ctx.is_unresolved(val):
                    ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="functions",
        kind="cloud_function",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_app_engine_standard_version(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    iclass = ctx.get("instance_class")
    if iclass:
        attributes["instance_class"] = iclass
        if ctx.is_unresolved(iclass):
            ctx.add_assumption(f"Unresolved attribute instance_class: '{iclass}'")

    for scaling_type in ("automatic_scaling", "basic_scaling", "manual_scaling"):
        scaling_list = ctx.attrs.get(scaling_type, [])
        if isinstance(scaling_list, list) and scaling_list:
            attributes["scaling_type"] = scaling_type
            scaling_blk = scaling_list[0]
            if isinstance(scaling_blk, dict):
                for k, v in scaling_blk.items():
                    resolved_v = ctx.resolve(v)
                    if resolved_v is not None:
                        attributes[f"{scaling_type}_{k}"] = resolved_v
                        if ctx.is_unresolved(resolved_v):
                            ctx.add_assumption(
                                f"Unresolved attribute {scaling_type}_{k}: '{resolved_v}'"
                            )

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="appengine",
        kind="app_engine_standard_version",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_app_engine_flexible_version(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    resources_blk = ctx.attrs.get("resources")
    if isinstance(resources_blk, list) and resources_blk:
        resources_blk = resources_blk[0]
    if isinstance(resources_blk, dict):
        for field in ("cpu", "memory_gb", "disk_gb"):
            val = ctx.resolve(resources_blk.get(field))
            if val is not None:
                attributes[field] = val
                if ctx.is_unresolved(val):
                    ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")
    else:
        ctx.add_assumption("No resources configuration found; using defaults.")

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="appengine",
        kind="app_engine_flexible_version",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_app_engine_application(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="appengine",
        kind="google_app_engine_application",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
