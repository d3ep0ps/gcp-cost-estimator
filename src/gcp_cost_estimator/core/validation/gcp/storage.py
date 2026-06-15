# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_storage(
    r: Resource, _errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP GCS resources."""
    if r.kind == "gcs_bucket":
        sclass = r.attributes.get("storage_class")
        if sclass:
            sclass_upper = str(sclass).upper()
            if sclass_upper not in {"STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"}:
                warnings.append(
                    f"Resource '{r.resource_id}' has unrecognized storage_class '{sclass}'."
                )


def normalize_storage(r: Resource) -> None:
    """Normalize GCP GCS resources."""
    if r.kind == "gcs_bucket":
        sclass = r.attributes.get("storage_class")
        if sclass:
            sclass_upper = str(sclass).upper()
            if sclass_upper not in {"STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"}:
                r.attributes["storage_class"] = "STANDARD"
                r.assumptions.append(
                    "Defaulted storage_class to STANDARD "
                    f"(unrecognized storage_class '{sclass}' was specified)."
                )
            else:
                r.attributes["storage_class"] = sclass_upper
        else:
            r.attributes["storage_class"] = "STANDARD"
            r.assumptions.append(
                "Defaulted storage_class to STANDARD. Override attributes.storage_class "
                "(NEARLINE/COLDLINE/ARCHIVE for cold data)."
            )

        # Apply representative defaults
        if "size_gb" not in r.usage:
            r.usage["size_gb"] = 100
            r.assumptions.append(
                "Defaulted size_gb to 100 GB. Override usage.size_gb "
                "with your expected data volume."
            )
        else:
            try:
                r.usage["size_gb"] = float(r.usage["size_gb"])
            except (ValueError, TypeError):
                r.usage["size_gb"] = 100
                r.assumptions.append("Invalid size_gb specified; defaulted size_gb to 100 GB.")

        if "monthly_class_a_ops" not in r.usage:
            r.usage["monthly_class_a_ops"] = 10_000
            r.assumptions.append(
                "Defaulted monthly_class_a_ops to 10000. Override "
                "usage.monthly_class_a_ops (~300 writes/day assumed)."
            )
        else:
            try:
                r.usage["monthly_class_a_ops"] = int(r.usage["monthly_class_a_ops"])
            except (ValueError, TypeError):
                r.usage["monthly_class_a_ops"] = 10_000

        if "monthly_class_b_ops" not in r.usage:
            r.usage["monthly_class_b_ops"] = 100_000
            r.assumptions.append(
                "Defaulted monthly_class_b_ops to 100000. Override "
                "usage.monthly_class_b_ops (~3,000 reads/day assumed)."
            )
        else:
            try:
                r.usage["monthly_class_b_ops"] = int(r.usage["monthly_class_b_ops"])
            except (ValueError, TypeError):
                r.usage["monthly_class_b_ops"] = 100_000

        if "monthly_egress_gb" not in r.usage:
            r.usage["monthly_egress_gb"] = 10
            r.assumptions.append(
                "Defaulted monthly_egress_gb to 10 GB. Override "
                "usage.monthly_egress_gb with expected internet egress."
            )
        else:
            try:
                r.usage["monthly_egress_gb"] = float(r.usage["monthly_egress_gb"])
            except (ValueError, TypeError):
                r.usage["monthly_egress_gb"] = 10

        if "monthly_retrieval_gb" not in r.usage:
            r.usage["monthly_retrieval_gb"] = 0
        else:
            try:
                r.usage["monthly_retrieval_gb"] = float(r.usage["monthly_retrieval_gb"])
            except (ValueError, TypeError):
                r.usage["monthly_retrieval_gb"] = 0
