# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def parse_pubsub_topic(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="pubsub",
        kind="pubsub_topic",
        region="global",
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_pubsub_subscription(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    retain = ctx.get("retain_acked_messages")
    if retain is not None:
        attributes["retain_acked_messages"] = retain

    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="pubsub",
        kind="pubsub_subscription",
        region="global",
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_pubsub_lite_topic(
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
        service="pubsub",
        kind="pubsub_lite_topic",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_pubsub_lite_subscription(
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
        service="pubsub",
        kind="pubsub_lite_subscription",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_dataflow_job(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    for k, v in ctx.attrs.items():
        val = ctx.resolve(v)
        if val is not None:
            attributes[k] = val

    mtype = ctx.get("machine_type")
    if mtype:
        attributes["machine_type"] = mtype
    max_w = ctx.get("max_workers")
    if max_w is not None:
        attributes["max_workers"] = max_w

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="dataflow",
        kind="dataflow_job",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_dataproc_cluster(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}

    # Master config
    master_configs = ctx.attrs.get("master_config", [])
    if isinstance(master_configs, dict):
        master_configs = [master_configs]
    if isinstance(master_configs, list) and master_configs:
        mc = master_configs[0]
        if isinstance(mc, dict):
            num_inst = ctx.resolve(mc.get("num_instances"))
            m_type = ctx.resolve(mc.get("machine_type"))
            if num_inst is not None:
                attributes["num_master_nodes"] = num_inst
            if m_type is not None:
                attributes["master_machine_type"] = m_type

    # Worker config
    worker_configs = ctx.attrs.get("worker_config", [])
    if isinstance(worker_configs, dict):
        worker_configs = [worker_configs]
    if isinstance(worker_configs, list) and worker_configs:
        wc = worker_configs[0]
        if isinstance(wc, dict):
            num_inst = ctx.resolve(wc.get("num_instances"))
            w_type = ctx.resolve(wc.get("machine_type"))
            if num_inst is not None:
                attributes["num_worker_nodes"] = num_inst
            if w_type is not None:
                attributes["worker_machine_type"] = w_type

    # Preemptible config
    preempt_configs = ctx.attrs.get("preemptible_worker_config", [])
    if isinstance(preempt_configs, dict):
        preempt_configs = [preempt_configs]
    if isinstance(preempt_configs, list) and preempt_configs:
        pc = preempt_configs[0]
        if isinstance(pc, dict):
            num_inst = ctx.resolve(pc.get("num_instances"))
            if num_inst is not None:
                attributes["num_preemptible_nodes"] = num_inst

    for k, v in ctx.attrs.items():
        if k not in ("master_config", "worker_config", "preemptible_worker_config"):
            val = ctx.resolve(v)
            if val is not None:
                attributes[k] = val

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()
    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="dataproc",
        kind="dataproc_cluster",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_dataproc_serverless_batch(
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
        service="dataproc",
        kind="dataproc_serverless_batch",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
