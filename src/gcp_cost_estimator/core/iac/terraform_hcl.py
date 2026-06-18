# SPDX-License-Identifier: Apache-2.0

import re
from pathlib import Path
from typing import Any

from gcp_cost_estimator.core.iac._hcl2_wrapper import load_hcl
from gcp_cost_estimator.core.iac.base import IaCParser, register_iac_parser
from gcp_cost_estimator.core.model import Resource, ResourceModel


def _extract_scalar(val: Any) -> Any:
    if isinstance(val, list):
        if len(val) == 1:
            return _extract_scalar(val[0])
        if len(val) == 0:
            return None
    if isinstance(val, str):
        return val.strip("\"'")
    return val


def _is_unresolved(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    return bool(re.search(r"\$\{.*?\}", val) or val.startswith("var.") or "count." in val)


class TerraformHclParser(IaCParser):
    """Parses static Terraform HCL files in a directory to extract resources."""

    def parse(self, path: str, _options: dict[str, Any] | None = None) -> ResourceModel:
        path_obj = Path(path)
        if not path_obj.is_dir():
            msg = f"Path '{path}' is not a directory. Terraform HCL parser requires a directory."
            raise ValueError(msg)

        tf_files = [f for f in path_obj.iterdir() if f.is_file() and f.suffix == ".tf"]

        merged_config: dict[str, Any] = {}
        for fpath in tf_files:
            try:
                config = load_hcl(fpath)
                for key, val in config.items():
                    if key not in merged_config:
                        merged_config[key] = []
                    if isinstance(val, list):
                        merged_config[key].extend(val)
            except Exception:
                pass

        var_defaults: dict[str, Any] = {}
        for var_dict in merged_config.get("variable", []):
            if isinstance(var_dict, dict):
                for var_name, var_info in var_dict.items():
                    clean_var_name = var_name.strip("\"'")
                    if isinstance(var_info, dict) and "default" in var_info:
                        var_defaults[clean_var_name] = _extract_scalar(var_info["default"])

        def resolve_value(val: Any) -> Any:
            scalar = _extract_scalar(val)
            if isinstance(scalar, str):
                match = re.match(r"^\$?\{?var\.([a-zA-Z0-9_-]+)\}?$", scalar)
                if match:
                    var_name = match.group(1)
                    if var_name in var_defaults:
                        return var_defaults[var_name]
            return scalar

        resources: list[Resource] = []

        for res_dict in merged_config.get("resource", []):
            if not isinstance(res_dict, dict):
                continue
            for res_type, instances in res_dict.items():
                res_type_clean = res_type.strip("\"'")
                if not isinstance(instances, dict):
                    continue
                for res_name, res_config in instances.items():
                    res_name_clean = res_name.strip("\"'")
                    if not isinstance(res_config, dict):
                        continue

                    if not res_type_clean.startswith("google_"):
                        continue

                    from gcp_cost_estimator.core.iac.gcp import RESOURCE_TYPE_MAP
                    from gcp_cost_estimator.core.iac.gcp.context import ParserContext

                    if res_type_clean == "google_bigquery_table":
                        has_dataset = False
                        for r_dict in merged_config.get("resource", []):
                            if isinstance(r_dict, dict) and "google_bigquery_dataset" in r_dict:
                                has_dataset = True
                                break
                        if not has_dataset:
                            import logging

                            logging.getLogger("gcp_cost_estimator").warning(
                                "Orphan BigQuery table '%s' found. "
                                "BigQuery pricing requires parent dataset location.",
                                res_name_clean,
                            )
                        continue

                    ctx = ParserContext(
                        attrs=res_config,
                        resolve=resolve_value,
                        is_unresolved=_is_unresolved,
                        assumptions=[],
                    )
                    labels = resolve_value(res_config.get("labels")) or {}
                    if not isinstance(labels, dict):
                        labels = {}

                    parser_fn = RESOURCE_TYPE_MAP.get(res_type_clean)
                    if parser_fn:
                        res = parser_fn(f"{res_type_clean}.{res_name_clean}", ctx, labels)
                        resources.append(res)
                    else:
                        parts = res_type_clean.split("_")
                        service = parts[1] if len(parts) > 1 else "other"
                        kind = res_type_clean

                        region = ctx.extract_region()
                        quantity = ctx.extract_quantity()

                        attributes = {}
                        for k, v in res_config.items():
                            resolved_v = resolve_value(v)
                            if resolved_v is not None:
                                attributes[k] = resolved_v

                        resources.append(
                            Resource(
                                provider="gcp",
                                resource_id=f"{res_type_clean}.{res_name_clean}",
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


register_iac_parser("terraform", TerraformHclParser)
