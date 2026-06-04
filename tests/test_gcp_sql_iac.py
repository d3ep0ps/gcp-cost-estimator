# SPDX-License-Identifier: Apache-2.0

import json

from gcp_billing_mcp.core.iac.base import get_iac_parser
from gcp_billing_mcp.core.iac.terraform_plan import parse_terraform
from gcp_billing_mcp.core.model import ResourceModel

# ---------------------------------------------------------------------------
# 1. HCL Parser Tests
# ---------------------------------------------------------------------------


def test_hcl_parses_google_sql_database_instance_enterprise_mysql(tmp_path) -> None:
    """Verify that static HCL parsing extracts standard MySQL Enterprise zonal instances."""
    hcl_content = """
    resource "google_sql_database_instance" "db" {
      name             = "my-db"
      database_version = "MYSQL_8_0"
      region           = "us-central1"

      settings {
        tier              = "db-custom-2-7680"
        edition           = "ENTERPRISE"
        availability_type = "ZONAL"
        disk_type         = "PD_SSD"
        disk_size         = 100

        backup_configuration {
          enabled = true
        }
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert isinstance(model, ResourceModel)
    assert len(model.resources) == 1

    res = model.resources[0]
    assert res.provider == "gcp"
    assert res.resource_id == "google_sql_database_instance.db"
    assert res.service == "sql"
    assert res.kind == "cloud_sql_instance"
    assert res.region == "us-central1"

    assert res.attributes.get("tier") == "db-custom-2-7680"
    assert res.attributes.get("edition") == "ENTERPRISE"
    assert res.attributes.get("database_version") == "MYSQL_8_0"
    assert res.attributes.get("availability_type") == "ZONAL"
    assert res.attributes.get("disk_type") == "PD_SSD"
    assert res.attributes.get("disk_size_gb") == 100
    assert res.attributes.get("backup_enabled") is True


def test_hcl_parses_enterprise_plus_postgres_with_regional_ha(tmp_path) -> None:
    """Verify that static HCL parses regional HA Enterprise Plus PostgreSQL database instances."""
    hcl_content = """
    resource "google_sql_database_instance" "db" {
      name             = "ha-db"
      database_version = "POSTGRES_15"
      region           = "europe-west1"

      settings {
        tier              = "db-custom-4-15360"
        edition           = "ENTERPRISE_PLUS"
        availability_type = "REGIONAL"
        disk_size         = 200
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    res = model.resources[0]
    assert res.attributes.get("edition") == "ENTERPRISE_PLUS"
    assert res.attributes.get("availability_type") == "REGIONAL"
    assert res.attributes.get("disk_size_gb") == 200
    assert res.attributes.get("backup_enabled") is None


def test_hcl_parses_sqlserver_with_tier_and_disk_size(tmp_path) -> None:
    """Verify that HCL parsing handles SQL Server version formatting."""
    hcl_content = """
    resource "google_sql_database_instance" "db" {
      name             = "mssql"
      database_version = "SQLSERVER_2019_STANDARD"
      region           = "us-east1"

      settings {
        tier              = "db-n1-standard-2"
        disk_type         = "PD_SSD"
        disk_size         = 50
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    res = model.resources[0]
    assert res.attributes.get("database_version") == "SQLSERVER_2019_STANDARD"
    assert res.attributes.get("tier") == "db-n1-standard-2"


def test_hcl_sql_unresolved_var_in_tier_flagged_not_assumed(tmp_path) -> None:
    """Verify unresolved variables in database tier are flagged in assumptions."""
    hcl_content = """
    resource "google_sql_database_instance" "db" {
      name             = "var-db"
      database_version = "MYSQL_8_0"
      region           = "us-central1"

      settings {
        tier = var.sql_instance_tier
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    res = model.resources[0]
    assert "sql_instance_tier" in res.attributes.get("tier", "")
    assert any(
        "unresolved" in a.lower() or "sql_instance_tier" in a.lower() for a in res.assumptions
    )


def test_hcl_sql_missing_database_version_flagged(tmp_path) -> None:
    """Verify that missing database version is extracted as empty and handled downstream."""
    hcl_content = """
    resource "google_sql_database_instance" "db" {
      name             = "no-ver"
      region           = "us-central1"
      settings {
        tier = "db-custom-2-7680"
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    res = model.resources[0]
    assert "database_version" not in res.attributes


# ---------------------------------------------------------------------------
# 2. Plan JSON Parser Tests
# ---------------------------------------------------------------------------


def test_plan_json_resolves_google_sql_database_instance(tmp_path) -> None:
    """Verify plan JSON parsing extracts google_sql_database_instance resources."""
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "google_sql_database_instance.db",
                        "mode": "managed",
                        "type": "google_sql_database_instance",
                        "name": "db",
                        "provider_name": "registry.terraform.io/hashicorp/google",
                        "values": {
                            "name": "my-db",
                            "database_version": "MYSQL_8_0",
                            "region": "us-central1",
                            "settings": [
                                {
                                    "tier": "db-custom-2-7680",
                                    "edition": "ENTERPRISE",
                                    "availability_type": "ZONAL",
                                    "disk_type": "PD_SSD",
                                    "disk_size": 100,
                                    "backup_configuration": [{"enabled": True}],
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan_data))

    model = parse_terraform(str(plan_file), mode="plan")

    assert len(model.resources) == 1
    res = model.resources[0]
    assert res.provider == "gcp"
    assert res.resource_id == "google_sql_database_instance.db"
    assert res.service == "sql"
    assert res.kind == "cloud_sql_instance"
    assert res.region == "us-central1"
    assert res.attributes.get("tier") == "db-custom-2-7680"
    assert res.attributes.get("edition") == "ENTERPRISE"
    assert res.attributes.get("database_version") == "MYSQL_8_0"
    assert res.attributes.get("availability_type") == "ZONAL"
    assert res.attributes.get("disk_type") == "PD_SSD"
    assert res.attributes.get("disk_size_gb") == 100
    assert res.attributes.get("backup_enabled") is True


def test_plan_json_sql_resolves_count_and_vars(tmp_path) -> None:
    """Verify plan JSON parses multiple count-based sql instances."""
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "google_sql_database_instance.db[0]",
                        "mode": "managed",
                        "type": "google_sql_database_instance",
                        "name": "db",
                        "index": 0,
                        "values": {
                            "name": "db-0",
                            "database_version": "MYSQL_8_0",
                            "region": "us-central1",
                            "settings": [{"tier": "db-custom-2-7680"}],
                        },
                    },
                    {
                        "address": "google_sql_database_instance.db[1]",
                        "mode": "managed",
                        "type": "google_sql_database_instance",
                        "name": "db",
                        "index": 1,
                        "values": {
                            "name": "db-1",
                            "database_version": "MYSQL_8_0",
                            "region": "us-central1",
                            "settings": [{"tier": "db-custom-2-7680"}],
                        },
                    },
                ]
            }
        },
    }
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan_data))

    model = parse_terraform(str(plan_file), mode="plan")

    assert len(model.resources) == 2
    assert model.resources[0].resource_id == "google_sql_database_instance.db[0]"
    assert model.resources[1].resource_id == "google_sql_database_instance.db[1]"


def test_plan_json_sql_module_resource_extracted(tmp_path) -> None:
    """Verify sql instance resources are extracted from plan nested inside modules."""
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "child_modules": [
                    {
                        "resources": [
                            {
                                "address": "module.db_module.google_sql_database_instance.db",
                                "mode": "managed",
                                "type": "google_sql_database_instance",
                                "name": "db",
                                "values": {
                                    "name": "mod-db",
                                    "database_version": "MYSQL_8_0",
                                    "region": "us-central1",
                                    "settings": [{"tier": "db-custom-2-7680"}],
                                },
                            }
                        ]
                    }
                ]
            }
        },
    }
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan_data))

    model = parse_terraform(str(plan_file), mode="plan")

    assert len(model.resources) == 1
    assert model.resources[0].resource_id == "module.db_module.google_sql_database_instance.db"
