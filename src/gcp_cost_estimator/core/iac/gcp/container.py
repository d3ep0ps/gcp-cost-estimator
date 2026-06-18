# SPDX-License-Identifier: Apache-2.0

import contextlib
from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def _parse_container_common(
    res_id: str,
    kind: str,
    ctx: ParserContext,
) -> Resource:
    attributes: dict[str, Any] = {}

    autopilot_list = ctx.attrs.get("enable_autopilot")
    if autopilot_list is not None:
        val = ctx.resolve(autopilot_list)
        if val is not None:
            attributes["enable_autopilot"] = bool(val)

    node_count = ctx.resolve(ctx.attrs.get("node_count")) or ctx.resolve(
        ctx.attrs.get("initial_node_count")
    )
    if node_count is not None:
        if ctx.is_unresolved(node_count):
            attributes["node_count"] = node_count
            ctx.add_assumption(f"Unresolved attribute node_count: '{node_count}'")
        else:
            with contextlib.suppress(ValueError, TypeError):
                attributes["node_count"] = int(node_count)

    node_configs = ctx.attrs.get("node_config", [])
    if isinstance(node_configs, list) and node_configs:
        nc = node_configs[0]
        if isinstance(nc, dict):
            mtype = ctx.resolve(nc.get("machine_type"))
            if mtype:
                attributes["machine_type"] = mtype
                if ctx.is_unresolved(mtype):
                    ctx.add_assumption(f"Unresolved attribute machine_type: '{mtype}'")

            disk_size = ctx.resolve(nc.get("disk_size_gb"))
            if disk_size is not None:
                if ctx.is_unresolved(disk_size):
                    attributes["disk_size_gb"] = disk_size
                    ctx.add_assumption(f"Unresolved attribute disk_size_gb: '{disk_size}'")
                else:
                    with contextlib.suppress(ValueError, TypeError):
                        attributes["disk_size_gb"] = int(disk_size)

            disk_type = ctx.resolve(nc.get("disk_type"))
            if disk_type:
                attributes["disk_type"] = disk_type
                if ctx.is_unresolved(disk_type):
                    ctx.add_assumption(f"Unresolved attribute disk_type: '{disk_type}'")

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="container",
        kind=kind,
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_container_cluster(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    return _parse_container_common(res_id, "gke_cluster", ctx)


def parse_container_node_pool(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    return _parse_container_common(res_id, "gke_node_pool", ctx)
