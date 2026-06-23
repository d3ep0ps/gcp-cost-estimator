# SPDX-License-Identifier: Apache-2.0

from typing import Any

from gcp_cost_estimator.core.model import Resource


def validate_firestore(
    r: Resource, _errors: list[str], warnings: list[str], _unpriced: list[dict[str, Any]]
) -> None:
    """Validate GCP Firestore resources."""
    if r.kind == "firestore_database":
        db_type = r.attributes.get("database_type", "FIRESTORE_NATIVE")
        if db_type not in {"FIRESTORE_NATIVE", "DATASTORE_MODE"}:
            warnings.append(
                f"Resource '{r.resource_id}' has unrecognized database_type '{db_type}'."
            )


def normalize_firestore(r: Resource) -> None:
    """Normalize GCP Firestore resources."""
    if r.kind == "firestore_database":
        db_type = r.attributes.get("database_type")
        if db_type:
            db_type_upper = str(db_type).upper()
            if db_type_upper not in {"FIRESTORE_NATIVE", "DATASTORE_MODE"}:
                r.attributes["database_type"] = "FIRESTORE_NATIVE"
                msg = (
                    "Defaulted database_type to FIRESTORE_NATIVE "
                    f"(unrecognized database_type '{db_type}' was specified)."
                )
                r.assumptions.append(msg)
            else:
                r.attributes["database_type"] = db_type_upper
        else:
            r.attributes["database_type"] = "FIRESTORE_NATIVE"
            r.assumptions.append("Defaulted database_type to FIRESTORE_NATIVE.")

        # Normalise Firestore location IDs to GCP regions
        if r.region:
            location_map = {
                "us-central": "us-central1",
                "europe-west": "europe-west1",
                "asia-northeast": "asia-northeast1",
            }
            r.region = location_map.get(r.region.lower(), r.region)

        # Usage defaults
        for field, val in [
            ("storage_gb", 1),
            ("monthly_reads", 500000),
            ("monthly_writes", 100000),
            ("monthly_deletes", 10000),
            ("monthly_egress_gb", 0),
        ]:
            if field not in r.usage:
                r.usage[field] = val
                r.assumptions.append(f"Defaulted {field} to {val}.")
            else:
                try:
                    is_float = field in ("storage_gb", "monthly_egress_gb")
                    r.usage[field] = float(r.usage[field]) if is_float else int(r.usage[field])
                except ValueError, TypeError:
                    r.usage[field] = val
                    r.assumptions.append(f"Invalid {field}; defaulted to {val}.")

        r.assumptions.append(
            "Free tier (1 GB storage, 50K reads/day, 20K writes/day, "
            "20K deletes/day) not applied — list price only."
        )
