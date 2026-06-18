# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def parse_dns_managed_zone(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    visibility = ctx.get("visibility")
    if visibility:
        attributes["visibility"] = visibility
    else:
        attributes["visibility"] = "public"

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="dns",
        kind="dns_managed_zone",
        region="global",
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_nat_gateway(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    allocate_option = ctx.get("nat_ip_allocate_option")
    if allocate_option:
        attributes["nat_ip_allocate_option"] = allocate_option

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="nat",
        kind="nat_gateway",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_compute_address(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    addr_type = ctx.get("address_type")
    if addr_type:
        attributes["address_type"] = addr_type
    purpose = ctx.get("purpose")
    if purpose:
        attributes["purpose"] = purpose

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="vpc",
        kind="compute_address",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_compute_security_policy(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    rules = ctx.attrs.get("rule", [])
    if isinstance(rules, dict):
        attributes["rule_count"] = 1
    elif isinstance(rules, list):
        attributes["rule_count"] = len(rules)
    else:
        attributes["rule_count"] = 0

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="armor",
        kind="compute_security_policy",
        region="global",
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_compute_backend(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    cdn_policy = ctx.attrs.get("cdn_policy")
    if cdn_policy:
        service = "cdn"
        kind = "cloud_cdn_backend"
        attributes["cdn_enabled"] = True
    else:
        res_type = res_id.split(".")[0]
        parts = res_type.split("_")
        service = parts[1] if len(parts) > 1 else "other"
        kind = res_type

    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service=service,
        kind=kind,
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
