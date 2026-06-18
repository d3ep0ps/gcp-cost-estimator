# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.iac.gcp.context import ParserContext
from gcp_cost_estimator.core.model import AttachedResource, Resource


def parse_compute_instance(
    res_id: str,
    ctx: ParserContext,
    _labels: dict[str, str],
) -> Resource:
    attributes: dict[str, Any] = {}
    attached: list[AttachedResource] = []

    mtype = ctx.get("machine_type")
    if mtype:
        attributes["machine_type"] = mtype
        if ctx.is_unresolved(mtype):
            ctx.add_assumption(f"Unresolved attribute machine_type: '{mtype}'")
    else:
        ctx.add_assumption("No machine_type specified; fallback to e2-medium.")
        attributes["machine_type"] = "e2-medium"

    # Parse scheduling block (preemptible / spot)
    sched_list = ctx.attrs.get("scheduling", [])
    if isinstance(sched_list, list) and sched_list:
        sched = sched_list[0]
        if isinstance(sched, dict):
            preempt = ctx.resolve(sched.get("preemptible"))
            if preempt is not None:
                attributes["preemptible"] = preempt

    # Parse boot disks
    boot_disks = ctx.attrs.get("boot_disk", [])
    if isinstance(boot_disks, list):
        for bd in boot_disks:
            if not isinstance(bd, dict):
                continue
            init_params_list = bd.get("initialize_params", [])
            if isinstance(init_params_list, list) and init_params_list:
                ip = init_params_list[0]
                if isinstance(ip, dict):
                    dsize = (
                        ctx.resolve(ip.get("size"))
                        or ctx.resolve(ip.get("size_gb"))
                        or 10
                    )
                    dtype = ctx.resolve(ip.get("type")) or "pd-standard"

                    disk_kind = (
                        "ssd_persistent_disk"
                        if "ssd" in str(dtype).lower()
                        else "pd_persistent_disk"
                    )

                    try:
                        if ctx.is_unresolved(dsize):
                            size_val = 10
                            ctx.add_assumption(
                                f"Unresolved or invalid boot disk size '{dsize}': "
                                "default to 10 GB."
                            )
                        else:
                            size_val = int(dsize)
                    except (ValueError, TypeError):
                        size_val = 10
                        ctx.add_assumption(
                            f"Unresolved or invalid boot disk size '{dsize}': "
                            "default to 10 GB."
                        )

                    attached.append(
                        AttachedResource(
                            kind=disk_kind,
                            quantity=1,
                            attributes={"size_gb": size_val},
                        )
                    )

    region = ctx.extract_region()
    quantity = ctx.extract_quantity()

    return Resource(
        provider="gcp",
        resource_id=res_id,
        service="compute",
        kind="gce_instance",
        region=region,
        attributes=attributes,
        attached=attached,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )


def parse_compute_disk(
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
        service="compute",
        kind="google_compute_disk",
        region=region,
        attributes=attributes,
        quantity=quantity,
        assumptions=ctx.assumptions,
    )
