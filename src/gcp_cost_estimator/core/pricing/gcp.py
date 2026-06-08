# SPDX-License-Identifier: Apache-2.0

import re
import sqlite3
from typing import Any

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.registries import SkuMapper, register_sku_mapper
from gcp_cost_estimator.core.validate import parse_k8s_quantity

# ---------------------------------------------------------------------------
# ADR-009: Replace static MACHINE_SPECS with a rule-based resolver.
#
# Three-layer resolution chain:
#   Layer 1 — Rule engine: derive (vcpu, ram_gb) from {family}-{subtype}-{N} naming convention.
#              Covers all standard GCP machine families, including brand-new ones added by Google
#              AFTER this code was written — zero code change required.
#   Layer 2 — Static shared-core overrides: 5 irregular types that don't follow the naming rule.
#   Layer 3 — Custom machine type pattern: custom-N-MMMM and {family}-custom-N-MMMM.
#
# Source for ratio values: https://cloud.google.com/compute/docs/machine-resource
# ---------------------------------------------------------------------------

# RAM-per-vCPU ratios (GB) — exact values from GCP public documentation.
# These ratios are universal across all families EXCEPT N1 (see _FAMILY_SUBTYPE_OVERRIDES).
_SUBTYPE_RAM_RATIO: dict[str, float] = {
    "standard": 4.0,  # n2-standard-4  → 4 x 4.0 = 16 GB
    "highmem": 8.0,  # n2-highmem-4   → 4 x 8.0 = 32 GB
    "highcpu": 1.0,  # n2-highcpu-4   → 4 x 1.0 = 4 GB
    "megamem": 14.933,  # m1-megamem-96  → 96 x 14.933 ≈ 1433.6 GB
    "ultramem": 24.025,  # m1-ultramem-80 → 80 x 24.025 ≈ 1922.0 GB
}

# Per-family ratio overrides — only N1 breaks the universal ratio for each subtype.
# N1 was GCP's first generation and was designed before the universal ratios were standardised.
_FAMILY_SUBTYPE_OVERRIDES: dict[tuple[str, str], float] = {
    ("n1", "standard"): 3.75,  # n1-standard-4 → 4 x 3.75 = 15.0 GB (NOT 16.0)
    ("n1", "highmem"): 6.5,  # n1-highmem-4  → 4 x 6.5  = 26.0 GB
    ("n1", "highcpu"): 0.9,  # n1-highcpu-4  → 4 x 0.9  = 3.6 GB
}

# Shared-core types: these do NOT follow the {family}-{subtype}-{N} pattern.
# The set is very small and extremely stable — GCP has not added a new shared-core type in years.
_SHARED_CORE_SPECS: dict[str, tuple[int, float]] = {
    "e2-micro": (2, 1.0),  # 2 billing vCPUs (shared), 1 GB RAM
    "e2-small": (2, 2.0),  # 2 billing vCPUs (shared), 2 GB RAM
    "e2-medium": (2, 4.0),  # 2 billing vCPUs (shared), 4 GB RAM
    "f1-micro": (1, 0.6),  # N1 shared-core, 0.6 GB RAM
    "g1-small": (1, 1.7),  # N1 shared-core, 1.7 GB RAM
}

# Regex for standard machine type names: {family}-{subtype}-{N}
# family: 2+ alphanumeric chars starting with a letter (e.g. n2, n2d, t2d, c3d, z3)
# subtype: one or more lowercase letters (standard, highmem, highcpu, megamem, ultramem)
# N: integer vCPU count
# NOTE: the 'custom' keyword must not match as a subtype — it is handled by _CUSTOM_PATTERN.
_STANDARD_PATTERN = re.compile(r"^([a-z][a-z0-9]+)-([a-z]+)-(\d+)$")

# Regex for custom machine types: [family-]custom-N-MMMM
# Matches both bare "custom-4-8192" and prefixed "n2-custom-4-8192", "n1-custom-4-8192", etc.
# A family prefix is any 2+ char alphanumeric token followed by a dash, immediately before 'custom'.
_CUSTOM_PATTERN = re.compile(r"^(?:[a-z][a-z0-9]+-)?custom-(\d+)-(\d+)$")


def _derive_specs_from_name(mt: str) -> tuple[int, float] | None:
    """Layer 1: derive (vcpu, ram_gb) from GCP naming convention.

    Returns None if the machine type name does not match the standard pattern,
    or if the subtype is not in the ratio table (unknown subtype).
    """
    m = _STANDARD_PATTERN.match(mt)
    if not m:
        return None
    family, subtype, vcpu_str = m.group(1), m.group(2), m.group(3)
    vcpu = int(vcpu_str)
    # Family-specific override takes precedence over the universal subtype ratio.
    ratio = _FAMILY_SUBTYPE_OVERRIDES.get((family, subtype)) or _SUBTYPE_RAM_RATIO.get(subtype)
    if ratio is None:
        return None  # Unknown subtype — fall through to next layer
    return vcpu, vcpu * ratio


def resolve_machine_type_specs(machine_type: str) -> tuple[int, float]:
    """Resolve a GCP machine type name to (vcpu, ram_gb).

    Resolution order (ADR-009):
      1. Rule-based derivation from {family}-{subtype}-{N} naming convention.
         Handles all standard GCP families automatically, including future ones.
      2. Static overrides for shared-core types (e2-micro, e2-small, e2-medium,
         f1-micro, g1-small).
      3. Custom machine type pattern: custom-N-MMMM or {family}-custom-N-MMMM.

    Returns (0, 0.0) if unresolvable — the caller must add the resource to unpriced[].
    """
    mt = machine_type.strip().lower()

    # Layer 1: rule engine (covers ~95% of real-world usage)
    result = _derive_specs_from_name(mt)
    if result is not None:
        return result

    # Layer 2: shared-core static overrides
    if mt in _SHARED_CORE_SPECS:
        return _SHARED_CORE_SPECS[mt]

    # Layer 3: custom machine type pattern
    m = _CUSTOM_PATTERN.match(mt)
    if m:
        vcpu = int(m.group(1))
        ram_mb = int(m.group(2))
        return vcpu, ram_mb / 1024.0

    return 0, 0.0


def resolve_sql_tier_specs(tier: str) -> tuple[int, float]:
    """Resolve a Cloud SQL tier spec name to (vcpu, ram_gb).

    Resolution logic:
      1. If custom: parse db-custom-{N}-{M} -> (N, M/1024.0)
      2. If standard: strip the leading 'db-' and delegate to resolve_machine_type_specs.
      3. Return (0, 0.0) if unresolvable.
    """
    t = tier.strip().lower()
    if not t:
        return 0, 0.0

    # Custom machine tier pattern db-custom-{N}-{M}
    if t.startswith("db-custom-"):
        parts = t.split("-")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            vcpu = int(parts[2])
            ram_mb = int(parts[3])
            return vcpu, ram_mb / 1024.0

    # Standard machine tier: strip 'db-' and delegate to resolve_machine_type_specs
    if t.startswith("db-"):
        stripped = t[3:]
        return resolve_machine_type_specs(stripped)

    return 0, 0.0


class GcpSkuMapper(SkuMapper):
    """GCP-specific SKU mapper implementing the SkuMapper interface."""

    @classmethod
    def get_supported_billing_services(cls) -> list[str]:
        """Return the list of official billing service display names required by this provider."""
        return [
            "Compute Engine",
            "Cloud SQL",
            "Cloud Storage",
            "Kubernetes Engine",
            "BigQuery",
            "Cloud Run",
            "Cloud Functions",
            "App Engine",
        ]

    def _map_gce_compute(
        self,
        region: str,
        machine_type: str,
        node_count: int,
        disk_size_gb: float,
        disk_type: str,
        resource_quantity: int,
        resource_id: str,
        cursor: sqlite3.Cursor,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        vcpu, ram = resolve_machine_type_specs(machine_type)
        if vcpu == 0:
            unpriced.append(
                {
                    "resource_id": resource_id,
                    "reason": f"Unknown machine_type '{machine_type}'",
                }
            )
            return mappings, unpriced

        family_prefix = machine_type.split("-")[0].upper()

        # Retrieve CPU SKU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'CPU'
            """,
            (region,),
        )
        cpu_rows = cursor.fetchall()
        cpu_match = None
        for row in cpu_rows:
            if family_prefix in row[3].upper():
                cpu_match = row
                break
        if not cpu_match and cpu_rows:
            cpu_match = cpu_rows[0]

        if cpu_match:
            mappings.append(
                {
                    "sku_id": cpu_match[0],
                    "component": "vcpu",
                    "unit": cpu_match[1],
                    "unit_price": cpu_match[2],
                    "qty": float(vcpu) * node_count * resource_quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource_id,
                    "reason": (
                        f"No pricing data for machine family '{family_prefix.lower()}'"
                        f" in region '{region}' — vCPU SKU not found"
                    ),
                }
            )

        # Retrieve RAM SKU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = 'RAM'
            """,
            (region,),
        )
        ram_rows = cursor.fetchall()
        ram_match = None
        for row in ram_rows:
            if family_prefix in row[3].upper():
                ram_match = row
                break
        if not ram_match and ram_rows:
            ram_match = ram_rows[0]

        if ram_match:
            mappings.append(
                {
                    "sku_id": ram_match[0],
                    "component": "ram",
                    "unit": ram_match[1],
                    "unit_price": ram_match[2],
                    "qty": float(ram) * node_count * resource_quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource_id,
                    "reason": f"No matching RAM SKU found in region {region}",
                }
            )

        # Disk
        if disk_size_gb > 0:
            sku_group = "SSD" if "ssd" in disk_type.lower() else "PDStandard"
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = ?
                """,
                (region, sku_group),
            )
            disk_rows = cursor.fetchall()
            if disk_rows:
                disk_match = disk_rows[0]
                mappings.append(
                    {
                        "sku_id": disk_match[0],
                        "component": "storage",
                        "unit": disk_match[1],
                        "unit_price": disk_match[2],
                        "qty": float(disk_size_gb) * node_count * resource_quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource_id,
                        "reason": (
                            f"No matching storage SKU found for '{sku_group}' in region {region}"
                        ),
                    }
                )

        return mappings, unpriced

    def _map_gke_cluster(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        if region is None:
            return mappings, unpriced

        # Lookup flat management fee SKU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ?
            AND (description LIKE '%Kubernetes Engine%' OR description LIKE '%GKE%')
            """,
            (region,),
        )
        mgmt_rows = cursor.fetchall()
        mgmt_match = None
        for row in mgmt_rows:
            if "management fee" in row[3].lower():
                mgmt_match = row
                break
        if not mgmt_match and mgmt_rows:
            mgmt_match = mgmt_rows[0]

        if mgmt_match:
            runtime_hours = float(resource.usage.get("runtime_hours_per_month", 730.0))
            mappings.append(
                {
                    "sku_id": mgmt_match[0],
                    "component": "management_fee",
                    "unit": mgmt_match[1],
                    "unit_price": mgmt_match[2],
                    "qty": runtime_hours * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No GKE cluster management fee SKU found in region '{region}'",
                }
            )

        machine_type = resource.attributes.get("machine_type")
        node_count = int(resource.attributes.get("node_count", 0))
        if machine_type and node_count > 0:
            disk_size = float(resource.attributes.get("disk_size_gb", 0))
            disk_type = resource.attributes.get("disk_type", "pd-standard")
            node_mappings, node_unpriced = self._map_gce_compute(
                region=region,
                machine_type=machine_type,
                node_count=node_count,
                disk_size_gb=disk_size,
                disk_type=disk_type,
                resource_quantity=resource.quantity,
                resource_id=resource.resource_id,
                cursor=cursor,
            )
            mappings.extend(node_mappings)
            unpriced.extend(node_unpriced)

        return mappings, unpriced

    def _map_gke_node_pool(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        if region is None:
            return mappings, unpriced
        machine_type = resource.attributes.get("machine_type")
        node_count = int(resource.attributes.get("node_count", 3))
        disk_size = float(resource.attributes.get("disk_size_gb", 100))
        disk_type = resource.attributes.get("disk_type", "pd-standard")

        if not machine_type:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "Missing machine_type for GKE node pool",
                }
            )
            return mappings, unpriced

        node_mappings, node_unpriced = self._map_gce_compute(
            region=region,
            machine_type=machine_type,
            node_count=node_count,
            disk_size_gb=disk_size,
            disk_type=disk_type,
            resource_quantity=resource.quantity,
            resource_id=resource.resource_id,
            cursor=cursor,
        )
        mappings.extend(node_mappings)
        unpriced.extend(node_unpriced)

        return mappings, unpriced

    def map_resource_to_skus(
        self, resource: Resource
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Decompose a GCP resource (like a VM or PD) into cached billable SKU rates."""
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        if resource.provider != "gcp":
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"GcpSkuMapper cannot process provider '{resource.provider}'",
                }
            )
            return mappings, unpriced

        region = resource.region
        if not region:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "No region specified for GCE resource.",
                }
            )
            return mappings, unpriced

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 1. Compute Instance (GCE VM)
            if resource.service == "compute" and resource.kind == "gce_instance":
                mtype = resource.attributes.get("machine_type", "")
                vm_mappings, vm_unpriced = self._map_gce_compute(
                    region=region,
                    machine_type=mtype,
                    node_count=1,
                    disk_size_gb=0,
                    disk_type="",
                    resource_quantity=resource.quantity,
                    resource_id=resource.resource_id,
                    cursor=cursor,
                )
                mappings.extend(vm_mappings)
                unpriced.extend(vm_unpriced)

                # Process attached resources (like disks)
                for attached in resource.attached:
                    if "disk" in attached.kind.lower():
                        sku_group = "SSD" if "ssd" in attached.kind.lower() else "PDStandard"
                        cursor.execute(
                            """
                            SELECT sku_id, unit, unit_price, description
                            FROM pricing_cache
                            WHERE provider = 'gcp' AND region = ? AND sku_group = ?
                            """,
                            (region, sku_group),
                        )
                        disk_rows = cursor.fetchall()
                        if disk_rows:
                            disk_match = disk_rows[0]
                            size_gb = float(attached.attributes.get("size_gb", 0))
                            mappings.append(
                                {
                                    "sku_id": disk_match[0],
                                    "component": "storage",
                                    "unit": disk_match[1],
                                    "unit_price": disk_match[2],
                                    "qty": size_gb * attached.quantity * resource.quantity,
                                }
                            )
                        else:
                            unpriced.append(
                                {
                                    "resource_id": f"{resource.resource_id}/{attached.kind}",
                                    "reason": (
                                        f"No matching storage SKU found for '{attached.kind}' "
                                        f"in region {region}"
                                    ),
                                }
                            )
                    else:
                        unpriced.append(
                            {
                                "resource_id": f"{resource.resource_id}/{attached.kind}",
                                "reason": f"Unsupported attached resource kind '{attached.kind}'",
                            }
                        )

            elif resource.service == "container" and resource.kind == "gke_cluster":
                is_autopilot = resource.attributes.get("enable_autopilot", False)
                if is_autopilot:
                    unpriced.append(
                        {
                            "resource_id": resource.resource_id,
                            "reason": "Autopilot uses per-pod pricing; not yet modelled",
                        }
                    )
                else:
                    gke_mappings, gke_unpriced = self._map_gke_cluster(resource, cursor)
                    mappings.extend(gke_mappings)
                    unpriced.extend(gke_unpriced)

            elif resource.service == "container" and resource.kind == "gke_node_pool":
                pool_mappings, pool_unpriced = self._map_gke_node_pool(resource, cursor)
                mappings.extend(pool_mappings)
                unpriced.extend(pool_unpriced)

            elif resource.service == "sql" and resource.kind == "cloud_sql_instance":
                sql_mappings, sql_unpriced = self._map_cloud_sql(resource, cursor)
                mappings.extend(sql_mappings)
                unpriced.extend(sql_unpriced)
            elif resource.service == "storage" and resource.kind == "gcs_bucket":
                gcs_mappings, gcs_unpriced = self._map_gcs_bucket(resource, cursor)
                mappings.extend(gcs_mappings)
                unpriced.extend(gcs_unpriced)
            elif resource.service == "bigquery" and resource.kind == "bigquery_dataset":
                bq_mappings, bq_unpriced = self._map_bigquery_dataset(resource, cursor)
                mappings.extend(bq_mappings)
                unpriced.extend(bq_unpriced)
            elif resource.service == "run" and resource.kind == "cloud_run_service":
                run_mappings, run_unpriced = self._map_cloud_run_service(resource, cursor)
                mappings.extend(run_mappings)
                unpriced.extend(run_unpriced)
            elif resource.service == "run" and resource.kind == "cloud_run_job":
                run_mappings, run_unpriced = self._map_cloud_run_job(resource, cursor)
                mappings.extend(run_mappings)
                unpriced.extend(run_unpriced)
            elif resource.service == "functions" and resource.kind == "cloud_function":
                fn_mappings, fn_unpriced = self._map_cloud_function(resource, cursor)
                mappings.extend(fn_mappings)
                unpriced.extend(fn_unpriced)
            elif resource.service == "appengine" and resource.kind == "app_engine_standard_version":
                ae_mappings, ae_unpriced = self._map_app_engine_standard_version(resource, cursor)
                mappings.extend(ae_mappings)
                unpriced.extend(ae_unpriced)
            elif resource.service == "appengine" and resource.kind == "app_engine_flexible_version":
                ae_mappings, ae_unpriced = self._map_app_engine_flexible_version(resource, cursor)
                mappings.extend(ae_mappings)
                unpriced.extend(ae_unpriced)
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"Unsupported resource kind '{resource.kind}'",
                    }
                )
        finally:
            conn.close()

        return mappings, unpriced

    def _map_cloud_sql(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        tier = resource.attributes.get("tier", "")
        db_version = resource.attributes.get("database_version", "")
        edition = resource.attributes.get("edition", "ENTERPRISE").upper()
        availability_type = resource.attributes.get("availability_type", "ZONAL").upper()
        disk_type = resource.attributes.get("disk_type", "PD_SSD").upper()
        disk_size_gb = float(resource.attributes.get("disk_size_gb", 0))
        backup_enabled = bool(resource.attributes.get("backup_enabled", False))

        # 1. Resolve tier to CPU and RAM specs
        vcpu, ram_gb = resolve_sql_tier_specs(tier)
        if vcpu == 0:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"Unknown Cloud SQL tier '{tier}'",
                }
            )
            return mappings, unpriced

        # 2. Extract database family
        db_ver_upper = db_version.upper()
        if db_ver_upper.startswith("MYSQL_"):
            db_family = "mysql"
        elif db_ver_upper.startswith("POSTGRES_"):
            db_family = "postgres"
        elif db_ver_upper.startswith("SQLSERVER_"):
            db_family = "sqlserver"
        else:
            db_family = "unknown"

        # 3. Validate Edition / SQL Server combinations (ADR-010 constraint)
        if (
            edition == "ENTERPRISE_PLUS"
            and db_family == "sqlserver"
            and not db_ver_upper.endswith("_ENTERPRISE")
        ):
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        "Enterprise Plus SQL Server requires an Enterprise licence "
                        f"version, got '{db_version}'"
                    ),
                }
            )
            return mappings, unpriced

        # 4. Determine HA multiplier
        ha_mult = 2 if availability_type == "REGIONAL" else 1

        # 5. Look up CPU SKU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ?
            AND sku_group IN ('SQLGen2InstancesCPU', 'SQLInstancesCPU')
            """,
            (region,),
        )
        cpu_rows = cursor.fetchall()
        cpu_match = None

        for row in cpu_rows:
            desc = row[3].lower()
            if db_family == "sqlserver":
                family_match = "sql server" in desc or "sqlserver" in desc
            else:
                family_match = db_family in desc

            avail_match = availability_type.lower() in desc

            if edition == "ENTERPRISE_PLUS":
                ed_match = "enterprise plus" in desc or "ent plus" in desc or "entplus" in desc
            else:
                ed_match = (
                    "enterprise plus" not in desc
                    and "ent plus" not in desc
                    and "entplus" not in desc
                )

            if family_match and avail_match and ed_match:
                cpu_match = row
                break

        if not cpu_match and cpu_rows:
            cpu_match = cpu_rows[0]

        if cpu_match:
            mappings.append(
                {
                    "sku_id": cpu_match[0],
                    "component": "vcpu",
                    "unit": cpu_match[1],
                    "unit_price": cpu_match[2],
                    "qty": float(vcpu) * ha_mult * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching Cloud SQL CPU SKU found in region '{region}'",
                }
            )

        # 6. Look up RAM SKU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ?
            AND sku_group IN ('SQLGen2InstancesRAM', 'SQLInstancesRAM')
            """,
            (region,),
        )
        ram_rows = cursor.fetchall()
        ram_match = None

        for row in ram_rows:
            desc = row[3].lower()
            if db_family == "sqlserver":
                family_match = "sql server" in desc or "sqlserver" in desc
            elif db_family == "postgres":
                family_match = "postgres" in desc or "postgre" in desc
            else:
                family_match = db_family in desc

            avail_match = availability_type.lower() in desc

            if edition == "ENTERPRISE_PLUS":
                ed_match = "enterprise plus" in desc or "ent plus" in desc or "entplus" in desc
            else:
                ed_match = (
                    "enterprise plus" not in desc
                    and "ent plus" not in desc
                    and "entplus" not in desc
                )

            if family_match and avail_match and ed_match:
                ram_match = row
                break

        if not ram_match and ram_rows:
            ram_match = ram_rows[0]

        if ram_match:
            mappings.append(
                {
                    "sku_id": ram_match[0],
                    "component": "ram",
                    "unit": ram_match[1],
                    "unit_price": ram_match[2],
                    "qty": float(ram_gb) * ha_mult * resource.quantity,
                }
            )
        else:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"No matching Cloud SQL RAM SKU found in region '{region}'",
                }
            )

        # 7. Look up Storage SKU (SSD or HDD)
        sku_group = "SSD" if disk_type == "PD_SSD" else "PDStandard"
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND sku_group = ?
            """,
            (region, sku_group),
        )
        disk_rows = cursor.fetchall()
        disk_match = None

        for row in disk_rows:
            desc = row[3].lower()
            if db_family == "sqlserver":
                family_match = "sql server" in desc or "sqlserver" in desc
            else:
                family_match = db_family in desc
            if family_match:
                disk_match = row
                break

        if not disk_match and disk_rows:
            disk_match = disk_rows[0]

        if disk_match and disk_size_gb > 0:
            mappings.append(
                {
                    "sku_id": disk_match[0],
                    "component": "storage",
                    "unit": disk_match[1],
                    "unit_price": disk_match[2],
                    "qty": disk_size_gb * resource.quantity,
                }
            )
        elif disk_size_gb > 0:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        f"No matching Cloud SQL storage SKU ({disk_type}) "
                        f"found in region '{region}'"
                    ),
                }
            )

        # 8. SQL Server License SKU (if SQL Server)
        if db_family == "sqlserver":
            if "_ENTERPRISE" in db_ver_upper:
                lic_type = "enterprise"
            elif "_STANDARD" in db_ver_upper:
                lic_type = "standard"
            elif "_WEB" in db_ver_upper:
                lic_type = "web"
            else:
                lic_type = "express"

            if lic_type != "express":
                cursor.execute(
                    """
                    SELECT sku_id, unit, unit_price, description
                    FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ?
                    AND sku_group IN ('SQLInstancesLicense', 'SQLGen2InstancesLicense')
                    """,
                    (region,),
                )
                lic_rows = cursor.fetchall()

                if not lic_rows:
                    cursor.execute(
                        """
                        SELECT sku_id, unit, unit_price, description
                        FROM pricing_cache
                        WHERE provider = 'gcp' AND region = ?
                        AND (description LIKE '%license%' OR description LIKE '%licensing%')
                        """,
                        (region,),
                    )
                    lic_rows = cursor.fetchall()

                lic_match = None
                for row in lic_rows:
                    desc = row[3].lower()
                    if lic_type in desc:
                        lic_match = row
                        break

                if not lic_match and lic_rows:
                    lic_match = lic_rows[0]

                if lic_match:
                    mappings.append(
                        {
                            "sku_id": lic_match[0],
                            "component": "license",
                            "unit": lic_match[1],
                            "unit_price": lic_match[2],
                            "qty": float(vcpu) * ha_mult * resource.quantity,
                        }
                    )
                else:
                    unpriced.append(
                        {
                            "resource_id": resource.resource_id,
                            "reason": (
                                f"No matching SQL Server license SKU ({lic_type}) "
                                f"found in region '{region}'"
                            ),
                        }
                    )

        # 9. Backup Storage SKU (if backups enabled)
        if backup_enabled and disk_size_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'Backup'
                """,
                (region,),
            )
            backup_rows = cursor.fetchall()
            backup_match = None

            for row in backup_rows:
                desc = row[3].lower()
                if db_family in desc:
                    backup_match = row
                    break

            if not backup_match and backup_rows:
                backup_match = backup_rows[0]

            if backup_match:
                mappings.append(
                    {
                        "sku_id": backup_match[0],
                        "component": "backup",
                        "unit": backup_match[1],
                        "unit_price": backup_match[2],
                        "qty": disk_size_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching Cloud SQL backup SKU found in region '{region}'",
                    }
                )

        return mappings, unpriced

    def _map_gcs_bucket(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        sclass = resource.attributes.get("storage_class", "STANDARD").upper()

        size_gb = float(resource.usage.get("size_gb", 0))
        monthly_class_a_ops = float(resource.usage.get("monthly_class_a_ops", 0))
        monthly_class_b_ops = float(resource.usage.get("monthly_class_b_ops", 0))
        monthly_egress_gb = float(resource.usage.get("monthly_egress_gb", 0))
        monthly_retrieval_gb = float(resource.usage.get("monthly_retrieval_gb", 0))

        if sclass not in {"STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"}:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": f"Unsupported storage class '{sclass}' for GCS bucket",
                }
            )
            return mappings, unpriced

        # 1. Emit storage SKU if size_gb > 0
        if size_gb > 0:
            sku_group = f"{sclass.capitalize()}Storage"
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = ?
                """,
                (region, sku_group),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "storage",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": size_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": (
                            f"No matching GCS storage SKU found for '{sclass}' in region '{region}'"
                        ),
                    }
                )

        # 2. Emit Class A ops SKU if monthly_class_a_ops > 0
        if monthly_class_a_ops > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'StorageOperations'
                AND (description LIKE '%Class A%' OR description LIKE '%class a%')
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "class_a_ops",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": (monthly_class_a_ops / 10000.0) * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching Class A operations SKU found in region '{region}'",
                    }
                )

        # 3. Emit Class B ops SKU if monthly_class_b_ops > 0
        if monthly_class_b_ops > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'StorageOperations'
                AND (description LIKE '%Class B%' OR description LIKE '%class b%')
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "class_b_ops",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": (monthly_class_b_ops / 10000.0) * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching Class B operations SKU found in region '{region}'",
                    }
                )

        # 4. Emit egress SKU if monthly_egress_gb > 0
        if monthly_egress_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'Egress'
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "egress",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": monthly_egress_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching egress SKU found in region '{region}'",
                    }
                )

        # 5. Emit retrieval fee SKU if monthly_retrieval_gb > 0 and storage class is cold
        if monthly_retrieval_gb > 0 and sclass in {"NEARLINE", "COLDLINE", "ARCHIVE"}:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'StorageRetrieval'
                AND (description LIKE ? OR description LIKE ?)
                """,
                (region, f"%{sclass.capitalize()}%", f"%{sclass.lower()}%"),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "retrieval",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": monthly_retrieval_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": (
                            f"No matching retrieval SKU found for '{sclass}' in region '{region}'"
                        ),
                    }
                )

        return mappings, unpriced

    def _map_bigquery_dataset(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        if not region:
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": "Missing region for BigQuery dataset",
                }
            )
            return mappings, unpriced

        pricing_model = resource.attributes.get("pricing_model", "on-demand")
        if pricing_model == "capacity":
            unpriced.append(
                {
                    "resource_id": resource.resource_id,
                    "reason": (
                        "Capacity pricing requires slot commitments; not statically estimable"
                    ),
                }
            )
            return mappings, unpriced

        active_storage_gb = float(resource.usage.get("active_storage_gb", 0))
        long_term_storage_gb = float(resource.usage.get("long_term_storage_gb", 0))
        monthly_query_tb = float(resource.usage.get("monthly_query_tb", 0))
        monthly_streaming_gb = float(resource.usage.get("monthly_streaming_gb", 0))

        # 1. Active storage
        if active_storage_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
                AND (description LIKE '%Active%')
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "active_storage",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": active_storage_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching active storage SKU found for region '{region}'",
                    }
                )

        # 2. Long-term storage
        if long_term_storage_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStorage'
                AND (description LIKE '%Long Term%')
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "long_term_storage",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": long_term_storage_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching long-term storage SKU found for region '{region}'",
                    }
                )

        # 3. Query scan (Analysis)
        if monthly_query_tb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryAnalysis'
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "query_scan",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": monthly_query_tb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": f"No matching query scan SKU found for region '{region}'",
                    }
                )

        # 4. Streaming insert
        if monthly_streaming_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'BigQueryStreaming'
                """,
                (region,),
            )
            rows = cursor.fetchall()
            if rows:
                match = rows[0]
                mappings.append(
                    {
                        "sku_id": match[0],
                        "component": "streaming_insert",
                        "unit": match[1],
                        "unit_price": match[2],
                        "qty": monthly_streaming_gb * resource.quantity,
                    }
                )
            else:
                unpriced.append(
                    {
                        "resource_id": resource.resource_id,
                        "reason": (f"No matching streaming insert SKU found for region '{region}'"),
                    }
                )

        return mappings, unpriced

    def _map_cloud_run_service(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        if not region:
            return mappings, unpriced

        cpu_str = parse_k8s_quantity(resource.attributes.get("cpu", "1"), is_cpu=True)
        memory_str = parse_k8s_quantity(resource.attributes.get("memory", "0.5"), is_cpu=False)
        try:
            cpu = float(cpu_str)
            memory = float(memory_str)
        except ValueError:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"Invalid cpu '{cpu_str}' or memory '{memory_str}'",
            })
            return mappings, unpriced

        cpu_idle = resource.attributes.get("cpu_idle", True)
        min_instances = int(resource.attributes.get("min_instance_count", 0))
        
        invocations = int(resource.usage.get("invocations_per_month", 10000))
        sec_per_inv = float(resource.usage.get("runtime_seconds_per_invocation", 1.0))
        active_seconds = float(invocations) * sec_per_inv

        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description, sku_group
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'cloud run'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if not rows:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No pricing data for Cloud Run in region '{region}'",
            })
            return mappings, unpriced

        cpu_active_sku = None
        cpu_idle_sku = None
        cpu_alloc_sku = None
        ram_active_sku = None
        ram_idle_sku = None
        ram_alloc_sku = None
        requests_sku = None
        gpu_sku = None

        for row in rows:
            sku_id, unit, unit_price, desc, sku_group = row
            desc_lower = desc.lower()
            if sku_group == "CPU":
                if "active" in desc_lower:
                    cpu_active_sku = row
                elif "idle" in desc_lower:
                    cpu_idle_sku = row
                elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                    cpu_alloc_sku = row
            elif sku_group == "RAM":
                if "active" in desc_lower:
                    ram_active_sku = row
                elif "idle" in desc_lower:
                    ram_idle_sku = row
                elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                    ram_alloc_sku = row
            elif sku_group == "Requests":
                requests_sku = row
            elif sku_group == "GPU":
                gpu_sku = row

        if not cpu_idle:
            target_cpu_sku = cpu_alloc_sku or cpu_active_sku
            if target_cpu_sku:
                mappings.append({
                    "sku_id": target_cpu_sku[0],
                    "component": "vcpu",
                    "unit": target_cpu_sku[1],
                    "unit_price": target_cpu_sku[2],
                    "qty": cpu * 730 * 3600 * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No CPU allocation SKU found for Cloud Run in region '{region}'",
                })

            target_ram_sku = ram_alloc_sku or ram_active_sku
            if target_ram_sku:
                mappings.append({
                    "sku_id": target_ram_sku[0],
                    "component": "ram",
                    "unit": target_ram_sku[1],
                    "unit_price": target_ram_sku[2],
                    "qty": memory * 730 * 3600 * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No RAM allocation SKU found for Cloud Run in region '{region}'",
                })
        else:
            if cpu_active_sku:
                mappings.append({
                    "sku_id": cpu_active_sku[0],
                    "component": "vcpu",
                    "unit": cpu_active_sku[1],
                    "unit_price": cpu_active_sku[2],
                    "qty": active_seconds * cpu * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No CPU active SKU found for Cloud Run in region '{region}'",
                })

            if ram_active_sku:
                mappings.append({
                    "sku_id": ram_active_sku[0],
                    "component": "ram",
                    "unit": ram_active_sku[1],
                    "unit_price": ram_active_sku[2],
                    "qty": active_seconds * memory * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No RAM active SKU found for Cloud Run in region '{region}'",
                })

            if min_instances > 0:
                total_cpu_warm = float(min_instances) * cpu * 730 * 3600
                total_ram_warm = float(min_instances) * memory * 730 * 3600
                
                cpu_idle_qty = max(0.0, total_cpu_warm - (active_seconds * cpu))
                ram_idle_qty = max(0.0, total_ram_warm - (active_seconds * memory))

                if cpu_idle_sku:
                    mappings.append({
                        "sku_id": cpu_idle_sku[0],
                        "component": "vcpu_idle",
                        "unit": cpu_idle_sku[1],
                        "unit_price": cpu_idle_sku[2],
                        "qty": cpu_idle_qty * resource.quantity,
                    })
                else:
                    unpriced.append({
                        "resource_id": resource.resource_id,
                        "reason": f"No CPU idle SKU found for Cloud Run in region '{region}'",
                    })

                if ram_idle_sku:
                    mappings.append({
                        "sku_id": ram_idle_sku[0],
                        "component": "ram_idle",
                        "unit": ram_idle_sku[1],
                        "unit_price": ram_idle_sku[2],
                        "qty": ram_idle_qty * resource.quantity,
                    })
                else:
                    unpriced.append({
                        "resource_id": resource.resource_id,
                        "reason": f"No RAM idle SKU found for Cloud Run in region '{region}'",
                    })

        if requests_sku:
            mappings.append({
                "sku_id": requests_sku[0],
                "component": "requests",
                "unit": requests_sku[1],
                "unit_price": requests_sku[2],
                "qty": float(invocations) * resource.quantity,
            })

        gpu_type = resource.attributes.get("gpu_type")
        gpu_count_str = resource.attributes.get("gpu_count", "0")
        try:
            gpu_count = int(gpu_count_str)
        except ValueError:
            gpu_count = 0

        if gpu_type and gpu_count > 0:
            if gpu_sku:
                gpu_seconds = (730 * 3600) if not cpu_idle else active_seconds
                mappings.append({
                    "sku_id": gpu_sku[0],
                    "component": "gpu",
                    "unit": gpu_sku[1],
                    "unit_price": gpu_sku[2],
                    "qty": float(gpu_count) * gpu_seconds * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No GPU SKU found for Cloud Run in region '{region}'",
                })

        return mappings, unpriced

    def _map_cloud_run_job(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        region = resource.region
        if not region:
            return mappings, unpriced

        cpu_str = parse_k8s_quantity(resource.attributes.get("cpu", "1"), is_cpu=True)
        memory_str = parse_k8s_quantity(resource.attributes.get("memory", "0.5"), is_cpu=False)
        try:
            cpu = float(cpu_str)
            memory = float(memory_str)
        except ValueError:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"Invalid cpu '{cpu_str}' or memory '{memory_str}'",
            })
            return mappings, unpriced

        task_count = int(resource.usage.get("task_count", 1))
        seconds_per_task = float(resource.usage.get("runtime_seconds_per_task", 60.0))
        executions = int(resource.usage.get("executions_per_month", 100))

        billed_seconds_per_task = max(60.0, seconds_per_task)
        total_seconds = billed_seconds_per_task * float(task_count) * float(executions)

        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description, sku_group
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'cloud run'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if not rows:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No pricing data for Cloud Run in region '{region}'",
            })
            return mappings, unpriced

        cpu_alloc_sku = None
        cpu_active_sku = None
        ram_alloc_sku = None
        ram_active_sku = None
        gpu_sku = None

        for row in rows:
            sku_id, unit, unit_price, desc, sku_group = row
            desc_lower = desc.lower()
            if sku_group == "CPU":
                if "active" in desc_lower:
                    cpu_active_sku = row
                elif "idle" in desc_lower:
                    pass
                elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                    cpu_alloc_sku = row
            elif sku_group == "RAM":
                if "active" in desc_lower:
                    ram_active_sku = row
                elif "idle" in desc_lower:
                    pass
                elif "alloc" in desc_lower or "always on" in desc_lower or "allocation" in desc_lower:
                    ram_alloc_sku = row
            elif sku_group == "GPU":
                gpu_sku = row

        target_cpu_sku = cpu_alloc_sku or cpu_active_sku
        if target_cpu_sku:
            mappings.append({
                "sku_id": target_cpu_sku[0],
                "component": "vcpu",
                "unit": target_cpu_sku[1],
                "unit_price": target_cpu_sku[2],
                "qty": total_seconds * cpu * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No CPU allocation SKU found for Cloud Run in region '{region}'",
            })

        target_ram_sku = ram_alloc_sku or ram_active_sku
        if target_ram_sku:
            mappings.append({
                "sku_id": target_ram_sku[0],
                "component": "ram",
                "unit": target_ram_sku[1],
                "unit_price": target_ram_sku[2],
                "qty": total_seconds * memory * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No RAM allocation SKU found for Cloud Run in region '{region}'",
            })

        gpu_type = resource.attributes.get("gpu_type")
        gpu_count_str = resource.attributes.get("gpu_count", "0")
        try:
            gpu_count = int(gpu_count_str)
        except ValueError:
            gpu_count = 0

        if gpu_type and gpu_count > 0:
            if gpu_sku:
                mappings.append({
                    "sku_id": gpu_sku[0],
                    "component": "gpu",
                    "unit": gpu_sku[1],
                    "unit_price": gpu_sku[2],
                    "qty": float(gpu_count) * total_seconds * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No GPU SKU found for Cloud Run in region '{region}'",
                })

        return mappings, unpriced

    def _map_cloud_function(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []

        gen = resource.attributes.get("generation", "1st_gen")
        if gen == "2nd_gen":
            return self._map_cloud_run_service(resource, cursor)

        region = resource.region
        if not region:
            return mappings, unpriced

        memory_mb = resource.attributes.get("available_memory_mb", 256)
        try:
            memory_gb = float(resource.attributes.get("memory_gb", float(memory_mb) / 1024.0))
            cpu_ghz = float(resource.attributes.get("cpu_ghz", 0.4))
        except (ValueError, TypeError):
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": "Invalid memory/cpu attributes for function",
            })
            return mappings, unpriced

        invocations = int(resource.usage.get("invocations_per_month", 1_000_000))
        avg_execution_time_ms = float(resource.usage.get("avg_execution_time_ms", 100.0))

        import math
        rounded_duration_sec = math.ceil(avg_execution_time_ms / 100.0) * 0.1
        active_seconds = float(invocations) * rounded_duration_sec

        min_instances = int(resource.attributes.get("min_instances", 0))

        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description, sku_group
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'cloud functions'
            """,
            (region,),
        )
        rows = cursor.fetchall()
        if not rows:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No pricing data for Cloud Functions in region '{region}'",
            })
            return mappings, unpriced

        invocations_sku = None
        cpu_active_sku = None
        cpu_idle_sku = None
        ram_active_sku = None
        ram_idle_sku = None

        for row in rows:
            sku_id, unit, unit_price, desc, sku_group = row
            desc_lower = desc.lower()
            if sku_group == "Invocations" or "invocation" in desc_lower:
                invocations_sku = row
            elif sku_group == "GHz-second" or "ghz" in desc_lower:
                if "idle" in desc_lower:
                    cpu_idle_sku = row
                else:
                    cpu_active_sku = row
            elif sku_group == "GB-second" or "gb" in desc_lower:
                if "idle" in desc_lower:
                    ram_idle_sku = row
                else:
                    ram_active_sku = row

        if invocations_sku:
            mappings.append({
                "sku_id": invocations_sku[0],
                "component": "requests",
                "unit": invocations_sku[1],
                "unit_price": invocations_sku[2],
                "qty": float(invocations) * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No Invocations SKU found for Cloud Functions in region '{region}'",
            })

        if cpu_active_sku:
            mappings.append({
                "sku_id": cpu_active_sku[0],
                "component": "vcpu",
                "unit": cpu_active_sku[1],
                "unit_price": cpu_active_sku[2],
                "qty": active_seconds * cpu_ghz * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No active GHz-second CPU SKU found for Cloud Functions in region '{region}'",
            })

        if ram_active_sku:
            mappings.append({
                "sku_id": ram_active_sku[0],
                "component": "ram",
                "unit": ram_active_sku[1],
                "unit_price": ram_active_sku[2],
                "qty": active_seconds * memory_gb * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No active GB-second Memory SKU found for Cloud Functions in region '{region}'",
            })

        if min_instances > 0:
            total_idle_seconds = max(0.0, float(min_instances) * 730.0 * 3600.0 - active_seconds)
            
            target_cpu_idle_sku = cpu_idle_sku or cpu_active_sku
            if target_cpu_idle_sku:
                mappings.append({
                    "sku_id": target_cpu_idle_sku[0],
                    "component": "vcpu_idle",
                    "unit": target_cpu_idle_sku[1],
                    "unit_price": target_cpu_idle_sku[2],
                    "qty": total_idle_seconds * cpu_ghz * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No GHz-second CPU idle SKU found for Cloud Functions in region '{region}'",
                })

            target_ram_idle_sku = ram_idle_sku or ram_active_sku
            if target_ram_idle_sku:
                mappings.append({
                    "sku_id": target_ram_idle_sku[0],
                    "component": "ram_idle",
                    "unit": target_ram_idle_sku[1],
                    "unit_price": target_ram_idle_sku[2],
                    "qty": total_idle_seconds * memory_gb * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No GB-second Memory idle SKU found for Cloud Functions in region '{region}'",
                })

        return mappings, unpriced

    def _map_app_engine_standard_version(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []
        region = resource.region
        if not region:
            return mappings, unpriced

        iclass = resource.attributes.get("instance_class", "F1")
        iclass_upper = iclass.upper()

        multipliers = {
            "F1": 1, "F2": 2, "F4": 4, "F4_1G": 6,
            "B1": 1, "B2": 2, "B4": 4, "B4_1G": 6, "B8": 8
        }
        if iclass_upper not in multipliers:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"Unknown instance class '{iclass}' for App Engine standard",
            })
            return mappings, unpriced

        multiplier = multipliers[iclass_upper]
        if iclass_upper.startswith("F"):
            sku_group = "Standard Frontend Instances"
        else:
            sku_group = "Standard Backend Instances"

        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'app engine' AND sku_group = ?
            """,
            (region, sku_group),
        )
        rows = cursor.fetchall()
        if not rows:
            # Fallback search matching description
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
                  AND (description LIKE ? OR description LIKE ?)
                """,
                (region, f"%{sku_group}%", f"%{'Frontend' if iclass_upper.startswith('F') else 'Backend'}%"),
            )
            rows = cursor.fetchall()

        if not rows:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No pricing SKU found for App Engine standard {iclass_upper} in region '{region}'",
            })
        else:
            row = rows[0]
            # Accrual rule: instance-hours continue accruing for 15 minutes (+0.25h) tail per lifecycle event
            lifecycle_events = float(resource.usage.get("lifecycle_events_per_month", 0))
            hours = float(resource.usage.get("runtime_hours_per_month", 730.0))
            total_hours = hours + (lifecycle_events * 0.25)
            qty = total_hours * multiplier * resource.quantity

            mappings.append({
                "sku_id": row[0],
                "component": "instances",
                "unit": row[1],
                "unit_price": row[2],
                "qty": qty,
            })

        # Handle standard egress
        egress_gb = float(resource.usage.get("egress_gb", 0))
        if egress_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'Egress'
                """,
                (region,),
            )
            egress_rows = cursor.fetchall()

            if egress_rows:
                mappings.append({
                    "sku_id": egress_rows[0][0],
                    "component": "egress",
                    "unit": egress_rows[0][1],
                    "unit_price": egress_rows[0][2],
                    "qty": egress_gb * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No egress SKU found for App Engine standard in region '{region}'",
                })

        return mappings, unpriced

    def _map_app_engine_flexible_version(
        self, resource: Resource, cursor: sqlite3.Cursor
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        mappings: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []
        region = resource.region
        if not region:
            return mappings, unpriced

        cpu = int(resource.attributes.get("cpu", 1))
        memory_gb = float(resource.attributes.get("memory_gb", 3.75))
        hours = float(resource.usage.get("runtime_hours_per_month", 730.0))

        # vCPU
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'app engine' AND sku_group = 'Flexible CPU'
            """,
            (region,),
        )
        cpu_rows = cursor.fetchall()
        if not cpu_rows:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
                  AND (description LIKE '%Flexible%CPU%' OR description LIKE '%Flexible%vCPU%')
                """,
                (region,),
            )
            cpu_rows = cursor.fetchall()

        if cpu_rows:
            mappings.append({
                "sku_id": cpu_rows[0][0],
                "component": "vcpu",
                "unit": cpu_rows[0][1],
                "unit_price": cpu_rows[0][2],
                "qty": float(cpu) * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No Flexible CPU SKU found for App Engine in region '{region}'",
            })

        # RAM
        cursor.execute(
            """
            SELECT sku_id, unit, unit_price, description
            FROM pricing_cache
            WHERE provider = 'gcp' AND region = ? AND service = 'app engine' AND sku_group = 'Flexible RAM'
            """,
            (region,),
        )
        ram_rows = cursor.fetchall()
        if not ram_rows:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND service = 'app engine'
                  AND (description LIKE '%Flexible%RAM%' OR description LIKE '%Flexible%Memory%')
                """,
                (region,),
            )
            ram_rows = cursor.fetchall()

        if ram_rows:
            mappings.append({
                "sku_id": ram_rows[0][0],
                "component": "ram",
                "unit": ram_rows[0][1],
                "unit_price": ram_rows[0][2],
                "qty": memory_gb * resource.quantity,
            })
        else:
            unpriced.append({
                "resource_id": resource.resource_id,
                "reason": f"No Flexible RAM SKU found for App Engine in region '{region}'",
            })

        # Process attached resources (like disks)
        for attached in resource.attached:
            if "disk" in attached.kind.lower():
                sku_group = "SSD" if "ssd" in attached.kind.lower() else "PDStandard"
                cursor.execute(
                    """
                    SELECT sku_id, unit, unit_price, description
                    FROM pricing_cache
                    WHERE provider = 'gcp' AND region = ? AND sku_group = ?
                    """,
                    (region, sku_group),
                )
                disk_rows = cursor.fetchall()
                if disk_rows:
                    disk_match = disk_rows[0]
                    size_gb = float(attached.attributes.get("size_gb", 0))
                    mappings.append(
                        {
                            "sku_id": disk_match[0],
                            "component": "storage",
                            "unit": disk_match[1],
                            "unit_price": disk_match[2],
                            "qty": size_gb * attached.quantity * resource.quantity,
                        }
                    )
                else:
                    unpriced.append(
                        {
                            "resource_id": f"{resource.resource_id}/{attached.kind}",
                            "reason": (
                                f"No matching storage SKU found for '{attached.kind}' "
                                f"in region {region}"
                            ),
                        }
                    )
            else:
                unpriced.append(
                    {
                        "resource_id": f"{resource.resource_id}/{attached.kind}",
                        "reason": f"Unsupported attached resource kind '{attached.kind}'",
                    }
                )

        # Egress
        egress_gb = float(resource.usage.get("egress_gb", 0))
        if egress_gb > 0:
            cursor.execute(
                """
                SELECT sku_id, unit, unit_price, description
                FROM pricing_cache
                WHERE provider = 'gcp' AND region = ? AND sku_group = 'Egress'
                """,
                (region,),
            )
            egress_rows = cursor.fetchall()
            if egress_rows:
                mappings.append({
                    "sku_id": egress_rows[0][0],
                    "component": "egress",
                    "unit": egress_rows[0][1],
                    "unit_price": egress_rows[0][2],
                    "qty": egress_gb * resource.quantity,
                })
            else:
                unpriced.append({
                    "resource_id": resource.resource_id,
                    "reason": f"No egress SKU found in region '{region}'",
                })

        return mappings, unpriced


# Register the SKU mapper in global registry
register_sku_mapper("gcp", GcpSkuMapper)
