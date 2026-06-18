# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def parse_filestore_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    tier_val = ctx.get("tier")
    if tier_val is not None:
        attributes["tier"] = tier_val
        if ctx.is_unresolved(tier_val):
            ctx.add_assumption(f"Unresolved attribute tier: '{tier_val}'")

    file_shares = ctx.attrs.get("file_shares", [])
    if isinstance(file_shares, list) and file_shares:
        fs = file_shares[0]
        if isinstance(fs, dict):
            cap = ctx.resolve(fs.get("capacity_gb"))
            if cap is not None:
                attributes["capacity_gb"] = cap
                if ctx.is_unresolved(cap):
                    ctx.add_assumption(f"Unresolved attribute capacity_gb: '{cap}'")
    elif isinstance(file_shares, dict):
        cap = ctx.resolve(file_shares.get("capacity_gb"))
        if cap is not None:
            attributes["capacity_gb"] = cap
            if ctx.is_unresolved(cap):
                ctx.add_assumption(f"Unresolved attribute capacity_gb: '{cap}'")

    for k, v in ctx.attrs.items():
        if k not in ("tier", "file_shares"):
            val = ctx.resolve(v)
            if val is not None:
                attributes[k] = val

    region = ctx.extract_region()
    if region and len(region.split("-")) == 3 and len(region.split("-")[-1]) == 1:
        region = "-".join(region.split("-")[:-1])

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="filestore",
        kind="google_filestore_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_vertex_ai_endpoint(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    ded = ctx.get("dedicated_endpoint_enabled")
    if ded is not None:
        attributes["dedicated_endpoint_enabled"] = ded

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="vertex",
        kind="google_vertex_ai_endpoint",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_artifact_registry_repository(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    fmt = ctx.get("format")
    if fmt is not None:
        attributes["format"] = fmt

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="artifact",
        kind="google_artifact_registry_repository",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
