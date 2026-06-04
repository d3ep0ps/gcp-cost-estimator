import sqlite3
from unittest.mock import patch

import pytest

from gcp_billing_mcp.core.model import ResourceModel
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.service import estimate_infrastructure


@pytest.fixture
def populated_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with standard GCP billing SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    mock_skus = [
        # N2 vCPU in us-central1
        {
            "sku_id": "SKU-N2-CPU",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core",
        },
        # N2 RAM in us-central1
        {
            "sku_id": "SKU-N2-RAM",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram",
        },
    ]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_estimate_end_to_end_for_sample_model(populated_db: str) -> None:
    """Verify that estimate_infrastructure successfully resolves and returns an estimate."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "n2-standard-4"},
                "usage": {"runtime_hours_per_month": 730.0},
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_db, model)

    assert est.currency == "USD"
    assert est.pricing_snapshot == "2026-06-03T12:00:00Z"
    assert len(est.unpriced) == 0
    assert len(est.line_items) == 2

    # 0.0475 * 4 * 730 = 138.7
    cpu_item = next(item for item in est.line_items if item.component == "vcpu")
    assert cpu_item.monthly_cost == 138.7

    # (0.0063 / 730) * 16 * 730 = 0.1008? Wait!
    # (0.0063 / 730) * 16 * 730 = 0.0063 * 16 = 0.1008. Let's assert:
    ram_item = next(item for item in est.line_items if item.component == "ram")
    assert round(ram_item.monthly_cost, 4) == round(0.0063 * 16.0, 4)

    assert round(est.monthly_total, 4) == round(138.7 + 0.0063 * 16.0, 4)


def test_estimate_includes_disclaimer_and_snapshot_ts(populated_db: str) -> None:
    """Verify estimate contains proper disclaimers, metadata, and assumptions."""
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
    est = estimate_infrastructure(populated_db, model)

    assert est.disclaimer != ""
    assert "list price only" in est.disclaimer.lower()
    assert est.pricing_snapshot == "2026-06-03T12:00:00Z"
    # The normalizer will add defaulted usage to assumptions
    assert len(est.assumptions) > 0
    assert any("730" in a for a in est.assumptions)


def test_estimate_surfaces_unpriced_resources(populated_db: str) -> None:
    """Verify that unsupported/unpriced elements are surfaced in the unpriced list."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {"machine_type": "unknown-mt-999"},
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_db, model)

    assert est.monthly_total == 0.0
    assert len(est.line_items) == 0
    assert len(est.unpriced) == 1
    assert est.unpriced[0].resource_id == "vm-1"
    assert "unknown machine_type" in est.unpriced[0].reason.lower()


def test_estimate_validation_errors(populated_db: str) -> None:
    """Verify that validation errors are captured and populated in the unpriced list."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "us-central1",
                "attributes": {},  # missing machine_type
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_db, model)
    assert len(est.unpriced) == 1
    assert est.unpriced[0].resource_id == "vm-1"
    assert "no valid machine_type" in est.unpriced[0].reason.lower()


@patch("gcp_billing_mcp.core.service.get_cache_status")
def test_estimate_cache_status_error(mock_get_status, populated_db: str) -> None:
    """Verify that errors while fetching cache status are gracefully handled."""
    mock_get_status.side_effect = Exception("DB Connection failed")
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
    est = estimate_infrastructure(populated_db, model)
    assert est.pricing_snapshot == "unknown"


@patch("gcp_billing_mcp.core.service.get_sku_mapper")
def test_estimate_mapper_error(mock_get_mapper, populated_db: str) -> None:
    """Verify that errors while resolving SKU mapper are gracefully captured as unpriced."""
    mock_get_mapper.side_effect = Exception("Mapper registry error")
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
    est = estimate_infrastructure(populated_db, model)
    assert len(est.unpriced) == 1
    assert est.unpriced[0].resource_id == "vm-1"
    assert "Mapper registry error" in est.unpriced[0].reason


def test_estimate_validation_warnings(populated_db: str) -> None:
    """Verify that validation warnings are added to assumptions."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "region": "",  # missing region
                "attributes": {"machine_type": "n2-standard-4"},
            }
        ]
    }
    model = ResourceModel(**data)
    est = estimate_infrastructure(populated_db, model)
    assert len(est.assumptions) > 0
    assert any("missing region" in a for a in est.assumptions)
