# SPDX-License-Identifier: Apache-2.0

from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.validate import normalize_resource_model, validate_resource_model


def test_missing_region_produces_warning_not_error() -> None:
    """Verify that a resource missing 'region' produces a warning, but is still valid."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "attributes": {"machine_type": "n2-standard-4"},
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert any("region" in w.lower() for w in result["warnings"])


def test_invalid_machine_type_flagged() -> None:
    """Verify that an invalid/empty machine type is flagged as an error."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": ""},
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("machine_type" in e or "machine type" in e.lower() for e in result["errors"])


def test_normalization_canonicalizes_region_aliases() -> None:
    """Verify that regions like 'us-central-1' are canonicalized to 'us-central1'."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central-1",
                "attributes": {"machine_type": "n2-standard-4"},
            }
        ]
    }
    model = ResourceModel(**data)
    normalized = normalize_resource_model(model)
    assert normalized.resources[0].region == "us-central1"


def test_defaults_applied_are_recorded_in_assumptions() -> None:
    """Verify that defaulting runtime_hours_per_month to 730 adds an assumption."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
            }
        ]
    }
    model = ResourceModel(**data)
    normalized = normalize_resource_model(model)
    assert normalized.resources[0].usage.get("runtime_hours_per_month") == 730
    assert any("730" in a for a in normalized.resources[0].assumptions)


def test_secret_flagged_attributes_redacted() -> None:
    """Verify that attributes with keys containing 'secret' or 'password' are redacted."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-1",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-1-3840",
                    "admin_password": "super-secret-password-123",
                    "db_secret_key": "somekey",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    normalized = normalize_resource_model(model)
    assert normalized.resources[0].attributes["admin_password"] == "[REDACTED]"
    assert normalized.resources[0].attributes["db_secret_key"] == "[REDACTED]"
    assert normalized.resources[0].attributes["tier"] == "db-custom-1-3840"


def test_cloud_sql_instance_valid_enterprise_mysql() -> None:
    """Verify that a standard Cloud SQL Enterprise MySQL zonal instance is valid."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-1",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "edition": "ENTERPRISE",
                    "database_version": "MYSQL_8_0",
                    "availability_type": "ZONAL",
                    "disk_type": "PD_SSD",
                    "disk_size_gb": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_cloud_sql_instance_valid_enterprise_plus_postgres() -> None:
    """Verify that an Enterprise Plus PostgreSQL instance is valid."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-2",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-4-15360",
                    "edition": "ENTERPRISE_PLUS",
                    "database_version": "POSTGRES_15",
                    "disk_size_gb": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_cloud_sql_enterprise_plus_sql_server_enterprise_licence_only_accepted() -> None:
    """Verify that Enterprise Plus SQL Server with an Enterprise license version is accepted."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-3",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "edition": "ENTERPRISE_PLUS",
                    "database_version": "SQLSERVER_2022_ENTERPRISE",
                    "disk_size_gb": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True


def test_cloud_sql_enterprise_plus_sql_server_standard_licence_rejected() -> None:
    """Verify that Enterprise Plus SQL Server with a Standard (or Web/Express) license is rejected."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-4",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "edition": "ENTERPRISE_PLUS",
                    "database_version": "SQLSERVER_2022_STANDARD",
                    "disk_size_gb": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("enterprise license" in e.lower() for e in result["errors"])


def test_cloud_sql_missing_tier_flagged_as_error() -> None:
    """Verify that a Cloud SQL instance missing 'tier' in attributes is invalid."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-5",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "database_version": "MYSQL_8_0",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("tier" in e.lower() for e in result["errors"])


def test_cloud_sql_missing_database_version_flagged_as_error() -> None:
    """Verify that a Cloud SQL instance missing 'database_version' is invalid."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-6",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any(
        "database_version" in e.lower() or "database version" in e.lower() for e in result["errors"]
    )


def test_cloud_sql_ha_regional_recorded_in_model() -> None:
    """Verify that regional availability type is preserved."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-7",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "database_version": "MYSQL_8_0",
                    "availability_type": "REGIONAL",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    assert normalized.resources[0].attributes["availability_type"] == "REGIONAL"


def test_cloud_sql_defaults_applied_disk_type_ssd_and_730h() -> None:
    """Verify normalization defaults are applied and recorded in assumptions."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-8",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "database_version": "MYSQL_8_0",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    normalized = result["normalized_model"]
    assert normalized is not None
    res = normalized.resources[0]
    assert res.attributes["disk_type"] == "PD_SSD"
    assert res.attributes["availability_type"] == "ZONAL"
    assert res.attributes["backup_enabled"] is False
    assert res.usage["runtime_hours_per_month"] == 730

    # Check assumptions are recorded
    assert any("PD_SSD" in a for a in res.assumptions)
    assert any("ZONAL" in a for a in res.assumptions)
    assert any("backup" in a.lower() for a in res.assumptions)


def test_cloud_sql_hdd_storage_with_sqlserver_flagged_as_warning() -> None:
    """Verify that using HDD storage on SQL Server produces a warning."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-9",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "database_version": "SQLSERVER_2019_STANDARD",
                    "disk_type": "PD_HDD",
                    "disk_size_gb": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any(
        "hdd storage" in w.lower() or "sql server does not support hdd" in w.lower()
        for w in result["warnings"]
    )


def test_cloud_sql_disk_size_below_10gb_flagged_as_error() -> None:
    """Verify that a disk size below 10 GB is flagged as an error."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-10",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "database_version": "MYSQL_8_0",
                    "disk_size_gb": 5,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is False
    assert any("disk_size_gb" in e.lower() or "disk size" in e.lower() for e in result["errors"])


def test_cloud_sql_unrecognized_database_version_flagged_as_warning() -> None:
    """Verify that an unrecognized database_version prefix produces a warning."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-11",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "database_version": "ORACLE_12C",
                    "disk_size_gb": 100,
                },
            }
        ]
    }
    model = ResourceModel(**data)
    result = validate_resource_model(model)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any(
        "database_version" in w.lower() or "database version" in w.lower()
        for w in result["warnings"]
    )
