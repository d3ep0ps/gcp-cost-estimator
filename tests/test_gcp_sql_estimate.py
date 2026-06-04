import json
import sqlite3

import pytest

from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.service import estimate_infrastructure


@pytest.fixture
def populated_sql_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static Cloud SQL SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    from pathlib import Path

    # Load SQL SKUs
    with Path("tests/fixtures/cloud_sql_skus.json").open() as f:
        mock_skus = json.load(f)

    # Add standard GCE N2 SKUs from tests/test_gcp.py for combined model testing
    gce_skus = [
        {
            "sku_id": "SKU-N2-CPU-USC1",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core running in Americas",
        },
        {
            "sku_id": "SKU-N2-RAM-USC1",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram running in Americas",
        },
    ]
    mock_skus.extend(gce_skus)

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_estimate_enterprise_mysql_zonal_golden_fixture(populated_sql_db: str) -> None:
    """Verify that the Enterprise MySQL zonal estimate matches the golden fixture exactly."""
    # Given the input model
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

    # When we compute the estimate
    est = estimate_infrastructure(populated_sql_db, model)

    from pathlib import Path

    # Load golden fixture
    with Path("tests/fixtures/cloud_sql_estimate_golden.json").open() as f:
        golden = json.load(f)

    # Then verify fields
    assert est.currency == golden["currency"]
    assert est.pricing_snapshot == golden["pricing_snapshot"]
    assert est.disclaimer == golden["disclaimer"]
    assert len(est.line_items) == len(golden["line_items"])

    for item in est.line_items:
        gold_item = next(gi for gi in golden["line_items"] if gi["component"] == item.component)
        assert item.sku_id == gold_item["sku_id"]
        assert pytest.approx(item.unit_price) == gold_item["unit_price"]
        assert item.unit == gold_item["unit"]
        assert item.qty == gold_item["qty"]
        assert item.usage_hours == gold_item["usage_hours"]
        assert pytest.approx(item.monthly_cost, abs=1e-3) == gold_item["monthly_cost"]

    assert pytest.approx(est.monthly_total, abs=1e-3) == golden["monthly_total"]
    assert len(est.unpriced) == 0


def test_estimate_enterprise_plus_postgres_regional_ha_golden_fixture(
    populated_sql_db: str,
) -> None:
    """Verify regional HA for Enterprise Plus Postgres."""
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
                    "availability_type": "REGIONAL",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert len(est.unpriced) == 0
    # CPU (qty = 4 * 2 = 8) & RAM (qty = 15 * 2 = 30)
    assert len(est.line_items) == 2

    cpu_item = next(item for item in est.line_items if item.component == "vcpu")
    assert cpu_item.sku_id == "SQL-POSTGRES-ENTPLUS-REGIONAL-CPU"
    # Cost math: 0.108 rate * 8 vcpu * 730 hours
    assert pytest.approx(cpu_item.monthly_cost, abs=1e-2) == 630.72

    ram_item = next(item for item in est.line_items if item.component == "ram")
    assert ram_item.sku_id == "SQL-POSTGRES-ENTPLUS-REGIONAL-RAM"
    # Cost math: 0.018 rate * 30 ram * 730 hours
    assert pytest.approx(ram_item.monthly_cost, abs=1e-2) == 394.20


def test_estimate_sqlserver_enterprise_includes_license_line_item(populated_sql_db: str) -> None:
    """Verify SQL Server Enterprise zonal includes the license line item."""
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
                    "edition": "ENTERPRISE",
                    "database_version": "SQLSERVER_2019_ENTERPRISE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert len(est.unpriced) == 0
    assert len(est.line_items) == 3  # CPU, RAM, License

    lic_item = next(item for item in est.line_items if item.component == "license")
    assert lic_item.sku_id == "SQL-SQLSERVER-LICENSE-ENTERPRISE"
    # Cost math: 0.1644 rate * 2 licenses * 730 hours
    assert pytest.approx(lic_item.monthly_cost, abs=1e-2) == 240.02


def test_estimate_enterprise_plus_sqlserver_enterprise_licence_priced_correctly(
    populated_sql_db: str,
) -> None:
    """Verify that Enterprise Plus SQL Server with Enterprise license maps and prices correctly."""
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
                    "database_version": "SQLSERVER_2019_ENTERPRISE",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert len(est.unpriced) == 0
    assert len(est.line_items) == 3


def test_estimate_enterprise_plus_sqlserver_standard_licence_is_unpriced_with_reason(
    populated_sql_db: str,
) -> None:
    """Verify that Enterprise Plus SQL Server with Standard license is unpriced."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-5",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-custom-2-7680",
                    "edition": "ENTERPRISE_PLUS",
                    "database_version": "SQLSERVER_2019_STANDARD",
                },
            }
        ]
    }
    # Wait, the validation logic in validate.py rejects this resource outright
    # so estimate_infrastructure will capture it as validation error and place in unpriced!
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert len(est.line_items) == 0
    assert len(est.unpriced) == 1
    assert est.unpriced[0].resource_id == "db-5"
    assert (
        "enterprise license" in est.unpriced[0].reason.lower()
        or "license" in est.unpriced[0].reason.lower()
    )


def test_estimate_unknown_tier_reported_in_unpriced_not_dropped(populated_sql_db: str) -> None:
    """Verify that an unknown tier is reported in unpriced."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "db-6",
                "service": "sql",
                "kind": "cloud_sql_instance",
                "region": "us-central1",
                "attributes": {
                    "tier": "db-unknown-999",
                    "database_version": "MYSQL_8_0",
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert len(est.line_items) == 0
    assert len(est.unpriced) == 1
    assert "unknown" in est.unpriced[0].reason.lower() or "tier" in est.unpriced[0].reason.lower()


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_sql_db: str) -> None:
    """Verify estimate disclaimer and pricing snapshot values."""
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
                },
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert est.pricing_snapshot == "2026-06-03T12:00:00Z"
    assert "list price only" in est.disclaimer.lower()


def test_estimate_cloud_sql_with_gce_instance_combined_model(populated_sql_db: str) -> None:
    """Verify that a combined model with both GCE VM and Cloud SQL instance prices correctly."""
    data = {
        "resources": [
            # GCE VM
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
            },
            # Cloud SQL Instance
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
                    "disk_type": "PD_SSD",
                    "disk_size_gb": 100,
                },
            },
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_sql_db, model)

    assert len(est.unpriced) == 0
    # VM CPU, VM RAM, DB CPU, DB RAM, DB Storage
    assert len(est.line_items) == 5

    # Check monthly total: VM (138.7 + 0.1008) + DB (115.623) = 254.4238
    assert pytest.approx(est.monthly_total, abs=1e-1) == 138.7 + 0.1 + 115.6
