# SPDX-License-Identifier: Apache-2.0

import re
from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_bigtable(
    r: Resource, errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Bigtable resources."""
    if r.kind == "bigtable_instance":
        inst_type = r.attributes.get("instance_type", "PRODUCTION").upper()
        clusters = r.attributes.get("clusters")
        if not clusters:
            errors.append(f"Resource '{r.resource_id}' is missing cluster configuration.")
        else:
            for cl in clusters:
                if not cl.get("zone"):
                    errors.append(f"Resource '{r.resource_id}' cluster is missing zone.")

                num_nodes = cl.get("num_nodes")
                if inst_type == "DEVELOPMENT":
                    if num_nodes is not None:
                        try:
                            if int(num_nodes) != 1:
                                msg = (
                                    f"Resource '{r.resource_id}' is a "
                                    "DEVELOPMENT instance but num_nodes is not 1."
                                )
                                errors.append(msg)
                        except ValueError, TypeError:
                            msg = (
                                f"Resource '{r.resource_id}' is a "
                                "DEVELOPMENT instance but num_nodes is not 1."
                            )
                            errors.append(msg)
                elif inst_type == "PRODUCTION" and num_nodes is not None:
                    try:
                        if int(num_nodes) < 3:
                            msg = (
                                f"Resource '{r.resource_id}' cluster has "
                                "fewer than 3 nodes (recommended minimum for production)."
                            )
                            warnings.append(msg)
                    except ValueError, TypeError:
                        pass


def normalize_bigtable(r: Resource) -> None:
    """Normalize GCP Bigtable resources."""
    if r.kind == "bigtable_instance":
        if "instance_type" not in r.attributes:
            r.attributes["instance_type"] = "PRODUCTION"
            r.assumptions.append("Defaulted instance_type to PRODUCTION.")
        else:
            inst_type = str(r.attributes["instance_type"]).upper()
            if inst_type not in {"PRODUCTION", "DEVELOPMENT"}:
                r.attributes["instance_type"] = "PRODUCTION"
                msg = (
                    "Defaulted instance_type to PRODUCTION "
                    f"(unrecognized instance_type '{inst_type}' was specified)."
                )
                r.assumptions.append(msg)
            else:
                r.attributes["instance_type"] = inst_type

        # Cluster defaults & region derivation
        clusters = r.attributes.get("clusters")
        if clusters:
            for cl in clusters:
                # Default storage_type to SSD
                if "storage_type" not in cl:
                    cl["storage_type"] = "SSD"
                    r.assumptions.append("Defaulted storage_type to SSD.")
                else:
                    stype = str(cl["storage_type"]).upper()
                    if stype not in {"SSD", "HDD"}:
                        cl["storage_type"] = "SSD"
                        msg = (
                            "Defaulted storage_type to SSD "
                            f"(unrecognized storage_type '{stype}' was specified)."
                        )
                        r.assumptions.append(msg)
                    else:
                        cl["storage_type"] = stype

                # Default num_nodes
                if "num_nodes" not in cl:
                    if r.attributes["instance_type"] == "DEVELOPMENT":
                        cl["num_nodes"] = 1
                        msg = "Defaulted num_nodes to 1 for DEVELOPMENT instance."
                        r.assumptions.append(msg)
                    else:
                        cl["num_nodes"] = 3
                        r.assumptions.append("Defaulted num_nodes to 3.")
                else:
                    try:
                        cl["num_nodes"] = int(cl["num_nodes"])
                    except ValueError, TypeError:
                        is_dev = r.attributes["instance_type"] == "DEVELOPMENT"
                        cl["num_nodes"] = 1 if is_dev else 3

                # Derive region from zone (strip trailing zone letter like -a, -b, -c)
                zone = cl.get("zone")
                if zone:
                    reg = re.sub(r"-[a-z]$", "", str(zone).strip()).lower()
                    cl["region"] = reg

        if "storage_gb_per_cluster" not in r.usage:
            r.usage["storage_gb_per_cluster"] = 0
            r.assumptions.append("Defaulted storage_gb_per_cluster to 0.")
        else:
            try:
                r.usage["storage_gb_per_cluster"] = float(r.usage["storage_gb_per_cluster"])
            except ValueError, TypeError:
                r.usage["storage_gb_per_cluster"] = 0
                r.assumptions.append("Invalid storage_gb_per_cluster; defaulted to 0.")
