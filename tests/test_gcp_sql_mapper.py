# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3

import pytest

from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_sql_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Cloud SQL SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    from pathlib import Path

    with Path("tests/fixtures/cloud_sql_skus.json").open() as f:
        mock_skus = json.load(f)

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_cloud_sql_enterprise_mysql_maps_to_vcpu_and_ram_skus(populated_sql_db: str) -> None:
    """Verify that an Enterprise MySQL zonal instance maps to vCPU and RAM SKUs."""
    resource = Resource(
        provider="gcp",
        resource_id="db-1",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE",
            "database_version": "MYSQL_8_0",
            "availability_type": "ZONAL",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 2

    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert vcpu_map["sku_id"] == "SQL-MYSQL-ENT-ZONAL-CPU"
    assert vcpu_map["qty"] == 2.0  # 2 vCPUs

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SQL-MYSQL-ENT-ZONAL-RAM"
    assert ram_map["qty"] == 7.5  # 7.5 GB RAM


def test_cloud_sql_enterprise_plus_postgres_maps_to_correct_skus(populated_sql_db: str) -> None:
    """Verify that an Enterprise Plus PostgreSQL instance maps to Enterprise Plus SKUs."""
    resource = Resource(
        provider="gcp",
        resource_id="db-2",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-4-15360",
            "edition": "ENTERPRISE_PLUS",
            "database_version": "POSTGRES_15",
            "availability_type": "ZONAL",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 2

    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert vcpu_map["sku_id"] == "SQL-POSTGRES-ENTPLUS-ZONAL-CPU"
    assert vcpu_map["qty"] == 4.0

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SQL-POSTGRES-ENTPLUS-ZONAL-RAM"
    assert ram_map["qty"] == 15.0


def test_cloud_sql_sqlserver_maps_to_vcpu_ram_and_license_skus(populated_sql_db: str) -> None:
    """Verify that SQL Server instance maps to CPU, RAM, and its license SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="db-3",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE",
            "database_version": "SQLSERVER_2019_ENTERPRISE",
            "availability_type": "ZONAL",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # CPU, RAM, and License SKUs
    assert len(mappings) == 3

    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert vcpu_map["sku_id"] == "SQL-SQLSERVER-ENT-ZONAL-CPU"

    license_map = next(m for m in mappings if m["component"] == "license")
    assert license_map["sku_id"] == "SQL-SQLSERVER-LICENSE-ENTERPRISE"
    assert license_map["qty"] == 2.0  # 2 vCPUs licensing


def test_cloud_sql_ha_doubles_vcpu_and_ram_quantity(populated_sql_db: str) -> None:
    """Verify that regional HA doubles the quantity of vCPU and RAM SKUs."""
    resource = Resource(
        provider="gcp",
        resource_id="db-4",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE",
            "database_version": "MYSQL_8_0",
            "availability_type": "REGIONAL",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 2

    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert vcpu_map["sku_id"] == "SQL-MYSQL-ENT-REGIONAL-CPU"
    assert vcpu_map["qty"] == 4.0  # 2 vCPUs * 2 (HA)

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SQL-MYSQL-ENT-REGIONAL-RAM"
    assert ram_map["qty"] == 15.0  # 7.5 GB RAM * 2 (HA)


def test_cloud_sql_ha_does_not_double_storage(populated_sql_db: str) -> None:
    """Verify that regional HA does not double storage disk quantity."""
    resource = Resource(
        provider="gcp",
        resource_id="db-5",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE",
            "database_version": "MYSQL_8_0",
            "availability_type": "REGIONAL",
            "disk_size_gb": 100,
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # CPU, RAM, and Storage
    assert len(mappings) == 3

    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert (
        storage_map["sku_id"] == "SQL-MYSQL-SSD-ZONAL"
    )  # SSD is zonal SKU (shared disk SKU is zonal in Iowa)
    assert storage_map["qty"] == 100.0  # Not doubled!


def test_cloud_sql_ssd_storage_maps_to_ssd_sku(populated_sql_db: str) -> None:
    """Verify SSD disk type maps to the SSD SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="db-6",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "database_version": "MYSQL_8_0",
            "disk_type": "PD_SSD",
            "disk_size_gb": 150,
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "SQL-MYSQL-SSD-ZONAL"
    assert storage_map["qty"] == 150.0


def test_cloud_sql_hdd_storage_maps_to_hdd_sku(populated_sql_db: str) -> None:
    """Verify HDD disk type maps to the HDD SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="db-7",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "database_version": "MYSQL_8_0",
            "disk_type": "PD_HDD",
            "disk_size_gb": 200,
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "SQL-MYSQL-HDD-ZONAL"
    assert storage_map["qty"] == 200.0


def test_cloud_sql_backup_storage_mapped_when_enabled(populated_sql_db: str) -> None:
    """Verify backup storage is mapped when backup_enabled is true."""
    resource = Resource(
        provider="gcp",
        resource_id="db-8",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "database_version": "MYSQL_8_0",
            "backup_enabled": True,
            "disk_size_gb": 100,
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, _unpriced = mapper.map_resource_to_skus(resource)

    # CPU, RAM, Storage, Backup
    assert len(mappings) == 4

    backup_map = next(m for m in mappings if m["component"] == "backup")
    assert backup_map["sku_id"] == "SQL-MYSQL-BACKUP-ZONAL"
    assert backup_map["qty"] == 100.0


def test_cloud_sql_unresolvable_tier_reported_unpriced(populated_sql_db: str) -> None:
    """Verify that an invalid/unresolvable tier is added to unpriced list."""
    resource = Resource(
        provider="gcp",
        resource_id="db-9",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-invalid-tier",
            "database_version": "MYSQL_8_0",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "tier" in unpriced[0]["reason"].lower()


def test_cloud_sql_enterprise_plus_sqlserver_enterprise_licence_maps_correctly(
    populated_sql_db: str,
) -> None:
    """Verify that Enterprise Plus SQL Server with Enterprise license maps correctly."""
    resource = Resource(
        provider="gcp",
        resource_id="db-10",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE_PLUS",
            "database_version": "SQLSERVER_2019_ENTERPRISE",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 3  # CPU, RAM, License


def test_cloud_sql_enterprise_plus_sqlserver_standard_licence_reported_unpriced(
    populated_sql_db: str,
) -> None:
    """Verify that Enterprise Plus SQL Server with Standard license (unsupported combination) is unpriced."""
    resource = Resource(
        provider="gcp",
        resource_id="db-11",
        service="sql",
        kind="cloud_sql_instance",
        region="us-central1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE_PLUS",
            "database_version": "SQLSERVER_2019_STANDARD",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "licence" in unpriced[0]["reason"].lower() or "license" in unpriced[0]["reason"].lower()


def test_cloud_sql_region_specific_sku_selected(populated_sql_db: str) -> None:
    """Verify that regional CPU/RAM SKUs are selected depending on resource region."""
    resource = Resource(
        provider="gcp",
        resource_id="db-12",
        service="sql",
        kind="cloud_sql_instance",
        region="europe-west1",
        attributes={
            "tier": "db-custom-2-7680",
            "edition": "ENTERPRISE",
            "database_version": "MYSQL_8_0",
        },
    )
    mapper = GcpSkuMapper(populated_sql_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 2

    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert vcpu_map["sku_id"] == "SQL-MYSQL-ENT-ZONAL-CPU-EU"

    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SQL-MYSQL-ENT-ZONAL-RAM-EU"
