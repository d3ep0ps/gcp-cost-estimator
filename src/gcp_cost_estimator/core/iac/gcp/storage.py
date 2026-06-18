# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import Resource


def parse_storage_bucket(
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
        service="storage",
        kind="gcs_bucket",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
