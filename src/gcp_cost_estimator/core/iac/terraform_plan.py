# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any

from gcp_cost_estimator.core.iac.base import IaCParser, get_iac_parser, register_iac_parser
from gcp_cost_estimator.core.model import Resource, ResourceModel


class TerraformPlanParser(IaCParser):
    """Parses a resolved Terraform plan JSON payload (produced by terraform show -json)."""

    def parse(self, path: str, _options: dict[str, Any] | None = None) -> ResourceModel:
        path_obj = Path(path)
        if path_obj.is_file():
            with path_obj.open(encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(path)

        planned_values = data.get("planned_values", {})
        root_module = planned_values.get("root_module", {})

        raw_resources: list[dict[str, Any]] = []

        def extract_resources_from_module(module: dict[str, Any]) -> None:
            for r in module.get("resources", []):
                raw_resources.append(r)
            for child in module.get("child_modules", []):
                extract_resources_from_module(child)

        extract_resources_from_module(root_module)

        resources: list[Resource] = []
        for raw_res in raw_resources:
            res_type = raw_res.get("type", "")
            if not res_type.startswith("google_"):
                continue

            address = raw_res.get("address", "")
            values = raw_res.get("values", {})

            from gcp_cost_estimator.core.iac.gcp import RESOURCE_TYPE_MAP
            from gcp_cost_estimator.core.iac.gcp.context import ParserContext

            if res_type == "google_bigquery_table":
                has_dataset = any(r.get("type") == "google_bigquery_dataset" for r in raw_resources)
                if not has_dataset:
                    import logging

                    logging.getLogger("gcp_cost_estimator").warning(
                        "Orphan BigQuery table '%s' found. "
                        "BigQuery pricing requires parent dataset location.",
                        address,
                    )
                continue

            ctx = ParserContext(
                attrs=values,
                resolve=lambda x: x,
                is_unresolved=lambda _: False,
                assumptions=[],
            )
            labels = values.get("labels") or {}
            if not isinstance(labels, dict):
                labels = {}

            parser_fn = RESOURCE_TYPE_MAP.get(res_type)
            if parser_fn:
                res = parser_fn(address, ctx, labels)
                resources.append(res)
            else:
                parts = res_type.split("_")
                service = parts[1] if len(parts) > 1 else "other"
                kind = res_type

                region = ctx.extract_region()
                quantity = 1

                attributes = {}
                for k, v in values.items():
                    if v is not None:
                        attributes[k] = v

                resources.append(
                    Resource(
                        provider="gcp",
                        resource_id=address,
                        service=service,
                        kind=kind,
                        region=region,
                        attributes=attributes,
                        quantity=quantity,
                        assumptions=ctx.assumptions,
                    )
                )

        app_engine_region = None
        for res in resources:
            if res.kind in ("google_app_engine_application", "app_engine_application"):
                loc = res.attributes.get("location_id") or res.region
                if loc:
                    if loc == "us-central":
                        loc = "us-central1"
                    elif loc == "europe-west":
                        loc = "europe-west1"
                    app_engine_region = loc
                    res.region = loc

        if app_engine_region:
            for res in resources:
                if res.service == "appengine" and not res.region:
                    res.region = app_engine_region

        return ResourceModel(resources=resources)


register_iac_parser("terraform-plan", TerraformPlanParser)


def parse_terraform(path: str, mode: str = "auto") -> ResourceModel:
    """Convenience dispatcher to parse Terraform directory or plan JSON.

    If mode is "plan", parses as a plan JSON file.
    If mode is "hcl", parses as static HCL directory.
    If mode is "auto", inspects path:
      - If it is a file ending in .json or contains plan structure, parses as plan JSON.
      - Otherwise, parses as HCL directory.
    """
    resolved_mode = mode
    if mode == "auto":
        if Path(path).is_file() and (path.endswith(".json") or "plan" in path.lower()):
            resolved_mode = "plan"
        else:
            resolved_mode = "hcl"

    if resolved_mode == "plan":
        parser = get_iac_parser("terraform-plan")
    else:
        parser = get_iac_parser("terraform")

    return parser.parse(path)
