# SPDX-License-Identifier: Apache-2.0

import re
import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource, ResourceModel
from gcp_cost_estimator.core.pricing.gcp import (
    resolve_alloydb_instance_specs,
    resolve_machine_type_specs,
    resolve_sql_tier_specs,
)
from gcp_cost_estimator.core.registries import get_sku_mapper
from gcp_cost_estimator.core.service import estimate_infrastructure

# Standard vCPU counts to probe for suggestions (covers the vast majority of real workloads).
_CANDIDATE_VCPU_COUNTS = [1, 2, 4, 8, 16, 32, 48, 64, 96]
_CANDIDATE_SUBTYPES = ["standard", "highmem", "highcpu"]

# Map family prefix (uppercase, from SKU description) → lowercase family name in machine type.
_FAMILY_PREFIX_TO_NAME_RE = re.compile(r"^([A-Z][A-Z0-9]+)\b")


def suggest_cheaper_machine_types(db_path: str, resource: Resource) -> list[dict[str, Any]]:
    """Search for cheaper viable VM machine configurations matching or exceeding specs.

    Candidate machine types are derived from the SKU cache (CPU SKU descriptions in the
    resource's region), so the function automatically includes any machine family Google
    adds after this code was written — no code change required.
    """
    if resource.provider != "gcp":
        return []

    if resource.service == "compute" and resource.kind == "gce_instance":
        mtype = resource.attributes.get("machine_type", "")
        current_vcpu, current_ram = resolve_machine_type_specs(mtype)
        if current_vcpu == 0:
            return []

        # Price current instance to establish a baseline
        current_model = ResourceModel(resources=[resource])
        current_est = estimate_infrastructure(db_path, current_model)
        current_cost = current_est.monthly_total

        # Build candidate list from families present in the cache for this region.
        region = resource.region or ""
        families: set[str] = set()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT description FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'CPU'
                """,
                (region,),
            )
            for (desc,) in cursor.fetchall():
                m = _FAMILY_PREFIX_TO_NAME_RE.match(desc.strip())
                if m:
                    families.add(m.group(1).lower())
        finally:
            conn.close()

        suggestions: list[dict[str, Any]] = []

        for family in sorted(families):
            for subtype in _CANDIDATE_SUBTYPES:
                for n_vcpu in _CANDIDATE_VCPU_COUNTS:
                    name = f"{family}-{subtype}-{n_vcpu}"
                    if name == mtype:
                        continue
                    cand_vcpu, cand_ram = resolve_machine_type_specs(name)
                    if cand_vcpu == 0:
                        continue
                    # Must match or exceed both the vCPU count and RAM requirement.
                    if cand_vcpu >= current_vcpu and cand_ram >= current_ram:
                        candidate_resource = resource.model_copy(deep=True)
                        candidate_resource.attributes["machine_type"] = name
                        candidate_model = ResourceModel(resources=[candidate_resource])
                        candidate_est = estimate_infrastructure(db_path, candidate_model)
                        candidate_cost = candidate_est.monthly_total

                        if candidate_cost < current_cost:
                            suggestions.append(
                                {
                                    "machine_type": name,
                                    "vcpu": cand_vcpu,
                                    "ram_gb": cand_ram,
                                    "monthly_cost": candidate_cost,
                                    "monthly_savings": current_cost - candidate_cost,
                                }
                            )

        # Sort suggestions by cost (cheapest configuration first)
        suggestions.sort(key=lambda x: x["monthly_cost"])
        return suggestions

    if resource.service == "sql" and resource.kind == "cloud_sql_instance":
        tier = resource.attributes.get("tier", "")
        current_vcpu, current_ram = resolve_sql_tier_specs(tier)
        if current_vcpu == 0:
            return []

        # Price current instance to establish a baseline
        current_model = ResourceModel(resources=[resource])
        current_est = estimate_infrastructure(db_path, current_model)
        current_cost = current_est.monthly_total

        suggestions = []

        # Generate candidate custom tiers: db-custom-N-M
        # N: vCPU count, M: RAM in MB
        for cand_vcpu in _CANDIDATE_VCPU_COUNTS:
            if cand_vcpu >= current_vcpu:
                # RAM per vCPU must be between 0.9 GB and 6.5 GB.
                min_ram_gb = max(current_ram, 0.9 * cand_vcpu)
                max_ram_gb = 6.5 * cand_vcpu
                if min_ram_gb <= max_ram_gb:
                    ram_options = [min_ram_gb]
                    for r in [3.75 * cand_vcpu, 6.5 * cand_vcpu]:
                        if r >= current_ram and 0.9 * cand_vcpu <= r <= 6.5 * cand_vcpu:
                            ram_options.append(r)

                    # Deduplicate and round to nearest 256MB multiple
                    seen_mb = set()
                    for ram_gb in ram_options:
                        ram_mb = int(round(ram_gb * 1024 / 256.0) * 256)
                        if ram_mb not in seen_mb:
                            seen_mb.add(ram_mb)
                            cand_ram_gb = ram_mb / 1024.0

                            # Double check constraints
                            if cand_vcpu >= current_vcpu and cand_ram_gb >= current_ram:
                                name = f"db-custom-{cand_vcpu}-{ram_mb}"
                                if name == tier:
                                    continue

                                candidate_resource = resource.model_copy(deep=True)
                                candidate_resource.attributes["tier"] = name
                                candidate_model = ResourceModel(resources=[candidate_resource])
                                candidate_est = estimate_infrastructure(db_path, candidate_model)
                                candidate_cost = candidate_est.monthly_total

                                if candidate_cost < current_cost:
                                    suggestions.append(
                                        {
                                            "tier": name,
                                            "machine_type": name,  # For backward compatibility
                                            "vcpu": cand_vcpu,
                                            "ram_gb": cand_ram_gb,
                                            "monthly_cost": candidate_cost,
                                            "monthly_savings": current_cost - candidate_cost,
                                        }
                                    )

        # Sort suggestions by cost (cheapest configuration first)
        suggestions.sort(key=lambda x: x["monthly_cost"])
        return suggestions

    if resource.service == "bigquery" and resource.kind == "bigquery_dataset":
        active_gb = float(resource.usage.get("active_storage_gb", 0))
        if active_gb > 0:
            region = resource.region or "us"
            active_price = 0.02
            long_term_price = 0.01

            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT unit_price FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
                    AND (description LIKE '%Active%')
                    """,
                    (region,),
                )
                row = cursor.fetchone()
                if row:
                    active_price = row[0]

                cursor.execute(
                    """
                    SELECT unit_price FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
                    AND (description LIKE '%Long Term%')
                    """,
                    (region,),
                )
                row = cursor.fetchone()
                if row:
                    long_term_price = row[0]
            finally:
                conn.close()

            current_cost = active_gb * active_price
            lt_cost = active_gb * long_term_price
            savings = current_cost - lt_cost

            if savings > 0:
                return [
                    {
                        "recommendation": (
                            "Transition unmodified tables/partitions (90+ days) "
                            "to long-term storage to reduce active storage costs."
                        ),
                        "monthly_cost": lt_cost,
                        "monthly_savings": savings,
                    }
                ]
        return []

    if resource.service == "alloydb" and resource.kind == "alloydb_instance":
        cpu_count = resource.attributes.get("cpu_count")
        if cpu_count is None:
            return []
        try:
            current_cpu = int(cpu_count)
        except ValueError, TypeError:
            return []

        current_vcpu, current_ram = resolve_alloydb_instance_specs(current_cpu)
        if current_vcpu == 0:
            return []

        # Price current instance to establish a baseline
        current_model = ResourceModel(resources=[resource])
        current_est = estimate_infrastructure(db_path, current_model)
        current_cost = current_est.monthly_total

        instance_type = resource.attributes.get("instance_type", "PRIMARY").upper()
        current_nodes = int(resource.attributes.get("node_count", 1))

        req_vcpu = current_vcpu * current_nodes

        suggestions = []
        candidate_cpu_counts = [2, 4, 8, 16, 32, 64, 96, 128]

        if instance_type == "PRIMARY":
            for cand_cpu in candidate_cpu_counts:
                if cand_cpu == current_cpu:
                    continue
                cand_vcpu, cand_ram = resolve_alloydb_instance_specs(cand_cpu)
                if cand_vcpu >= current_vcpu and cand_ram >= current_ram:
                    candidate_resource = resource.model_copy(deep=True)
                    candidate_resource.attributes["cpu_count"] = cand_cpu
                    candidate_model = ResourceModel(resources=[candidate_resource])
                    candidate_est = estimate_infrastructure(db_path, candidate_model)
                    candidate_cost = candidate_est.monthly_total
                    if candidate_cost < current_cost:
                        suggestions.append(
                            {
                                "cpu_count": cand_cpu,
                                "node_count": 1,
                                "vcpu": cand_vcpu,
                                "ram_gb": cand_ram,
                                "monthly_cost": candidate_cost,
                                "monthly_savings": current_cost - candidate_cost,
                            }
                        )
        elif instance_type == "READ_POOL":
            for cand_cpu in candidate_cpu_counts:
                cand_vcpu, cand_ram = resolve_alloydb_instance_specs(cand_cpu)
                if cand_vcpu == 0:
                    continue
                for cand_nodes in range(1, 11):
                    if cand_cpu == current_cpu and cand_nodes == current_nodes:
                        continue
                    if cand_vcpu * cand_nodes >= req_vcpu:
                        candidate_resource = resource.model_copy(deep=True)
                        candidate_resource.attributes["cpu_count"] = cand_cpu
                        candidate_resource.attributes["node_count"] = cand_nodes
                        candidate_model = ResourceModel(resources=[candidate_resource])
                        candidate_est = estimate_infrastructure(db_path, candidate_model)
                        candidate_cost = candidate_est.monthly_total
                        if candidate_cost < current_cost:
                            suggestions.append(
                                {
                                    "cpu_count": cand_cpu,
                                    "node_count": cand_nodes,
                                    "vcpu": cand_vcpu,
                                    "ram_gb": cand_ram,
                                    "monthly_cost": candidate_cost,
                                    "monthly_savings": current_cost - candidate_cost,
                                }
                            )

        suggestions.sort(key=lambda x: x["monthly_cost"])
        return suggestions

    return []


def find_unpriced(db_path: str, model: ResourceModel) -> list[dict[str, Any]]:
    """Scan the resource model to identify support/mapping coverage gaps."""
    unpriced_list: list[dict[str, Any]] = []

    for r in model.resources:
        try:
            mapper = get_sku_mapper(r.provider, db_path)
            _, unpriced = mapper.map_resource_to_skus(r)
            for up in unpriced:
                unpriced_list.append(
                    {
                        "resource_id": r.resource_id,
                        "sub_resource_id": up.get("resource_id", r.resource_id),
                        "reason": up["reason"],
                    }
                )
        except Exception as e:
            unpriced_list.append(
                {
                    "resource_id": r.resource_id,
                    "reason": str(e),
                }
            )

    return unpriced_list
