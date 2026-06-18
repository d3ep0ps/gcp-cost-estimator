# SPDX-License-Identifier: Apache-2.0

import re
from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def parse_spanner_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for field in ("config", "num_nodes", "processing_units", "edition"):
        val = ctx.get(field)
        if val is not None:
            attributes[field] = val
            if ctx.is_unresolved(val):
                ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")

    region = ctx.extract_region()
    if not region:
        config_val = attributes.get("config")
        if config_val and isinstance(config_val, str):
            if config_val.startswith("regional-"):
                region = config_val[len("regional-") :]
            elif config_val.startswith("nam"):
                region = "us-central1"
            elif config_val.startswith("eur"):
                region = "europe-west1"
            elif config_val.startswith("asia"):
                region = "asia-east1"

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="spanner",
        kind="spanner_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_firestore_database(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    db_type = ctx.get("type")
    if db_type is not None:
        attributes["database_type"] = db_type
        if ctx.is_unresolved(db_type):
            ctx.add_assumption(f"Unresolved attribute type: '{db_type}'")

    region = ctx.extract_region()
    loc_id = ctx.get("location_id")
    if loc_id is not None:
        if not ctx.is_unresolved(loc_id):
            region = loc_id
        else:
            ctx.add_assumption(f"Unresolved attribute location_id: '{loc_id}'")

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="firestore",
        kind="firestore_database",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_redis_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for field in ("memory_size_gb", "tier", "region", "redis_version"):
        val = ctx.get(field)
        if val is not None:
            attributes[field] = val
            if ctx.is_unresolved(val):
                ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")

    region = ctx.extract_region()
    if not region and attributes.get("region"):
        region = attributes["region"]

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="memorystore",
        kind="redis_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_memorystore_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for field in ("instance_id", "location", "shard_count", "node_type", "mode"):
        val = ctx.get(field)
        if val is not None:
            attributes[field] = val
            if ctx.is_unresolved(val):
                ctx.add_assumption(f"Unresolved attribute {field}: '{val}'")

    region = ctx.extract_region()
    if not region and attributes.get("location"):
        region = attributes["location"]

    if region and len(region.split("-")) == 3 and len(region.split("-")[-1]) == 1:
        region = "-".join(region.split("-")[:-1])

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="memorystore",
        kind="memorystore_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_bigtable_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    inst_type = ctx.get("instance_type")
    if inst_type is not None:
        attributes["instance_type"] = inst_type
        if ctx.is_unresolved(inst_type):
            ctx.add_assumption(f"Unresolved attribute instance_type: '{inst_type}'")

    clusters_raw = ctx.attrs.get("cluster")
    region = ctx.extract_region()
    if clusters_raw:
        if not isinstance(clusters_raw, list):
            clusters_raw = [clusters_raw]
        clusters_list = []
        for cl in clusters_raw:
            if isinstance(cl, dict):
                cl_dict = {}
                for k, v in cl.items():
                    resolved_v = ctx.resolve(v)
                    cl_dict[k] = resolved_v
                    if resolved_v is not None and ctx.is_unresolved(resolved_v):
                        ctx.add_assumption(f"Unresolved attribute cluster_{k}: '{resolved_v}'")
                clusters_list.append(cl_dict)
        attributes["clusters"] = clusters_list

        if not region:
            first_cl = clusters_raw[0]
            if isinstance(first_cl, dict):
                first_zone = ctx.resolve(first_cl.get("zone"))
                if first_zone and not ctx.is_unresolved(first_zone):
                    region = re.sub(r"-[a-z]$", "", str(first_zone).strip()).lower()

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="bigtable",
        kind="bigtable_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_alloydb_cluster(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    initial_user = ctx.attrs.get("initial_user")
    if initial_user:
        if isinstance(initial_user, list) and initial_user:
            initial_user_blk = initial_user[0]
        else:
            initial_user_blk = initial_user
        if isinstance(initial_user_blk, dict):
            initial_user_blk_copy = dict(initial_user_blk)
            initial_user_blk_copy.pop("password", None)
            attributes["initial_user"] = initial_user_blk_copy

    for k, v in ctx.attrs.items():
        if k == "initial_user":
            continue
        resolved_v = ctx.resolve(v)
        if resolved_v is not None:
            attributes[k] = resolved_v

    region = ctx.extract_region()
    if not region and attributes.get("location"):
        region = attributes["location"]

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="alloydb",
        kind="alloydb_cluster",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_alloydb_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    itype = ctx.get("instance_type")
    if itype is not None:
        attributes["instance_type"] = itype
        if ctx.is_unresolved(itype):
            ctx.add_assumption(f"Unresolved attribute instance_type: '{itype}'")

    mconfig = ctx.attrs.get("machine_config")
    if mconfig:
        mconfig_blk = mconfig[0] if isinstance(mconfig, list) and mconfig else mconfig
        if isinstance(mconfig_blk, dict):
            cpu_count = ctx.resolve(mconfig_blk.get("cpu_count"))
            if cpu_count is not None:
                attributes["cpu_count"] = cpu_count
                if ctx.is_unresolved(cpu_count):
                    ctx.add_assumption(f"Unresolved attribute cpu_count: '{cpu_count}'")

    rpconfig = ctx.attrs.get("read_pool_config")
    if rpconfig:
        rpconfig_blk = rpconfig[0] if isinstance(rpconfig, list) and rpconfig else rpconfig
        if isinstance(rpconfig_blk, dict):
            node_count = ctx.resolve(rpconfig_blk.get("node_count"))
            if node_count is not None:
                attributes["node_count"] = node_count
                if ctx.is_unresolved(node_count):
                    ctx.add_assumption(f"Unresolved attribute node_count: '{node_count}'")

    cluster = ctx.get("cluster")
    region = ctx.extract_region()
    if cluster is not None:
        if isinstance(cluster, str) and "/clusters/" in cluster:
            cluster_id = cluster.split("/clusters/")[-1]
            attributes["cluster_ref"] = cluster_id
            if "/locations/" in cluster:
                loc_part = cluster.split("/locations/")[1].split("/")[0]
                if not region:
                    region = loc_part
        else:
            attributes["cluster_ref"] = cluster
            if ctx.is_unresolved(cluster):
                ctx.add_assumption(f"Unresolved attribute cluster: '{cluster}'")

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="alloydb",
        kind="alloydb_instance",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
