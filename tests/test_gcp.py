# SPDX-License-Identifier: Apache-2.0

import sqlite3

import pytest

from gcp_billing_mcp.core.model import AttachedResource, Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper, resolve_machine_type_specs


@pytest.fixture
def populated_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with standard GCP billing SKUs."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    mock_skus = [
        # N2 vCPU in us-central1
        {
            "sku_id": "SKU-N2-CPU-USC1",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",  # We will match based on group and description
            "description": "N2 Instance Core running in Americas",
        },
        # N2 RAM in us-central1
        {
            "sku_id": "SKU-N2-RAM-USC1",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram running in Americas",
        },
        # N2 vCPU in europe-west1 (region check)
        {
            "sku_id": "SKU-N2-CPU-EUW1",
            "service": "compute engine",
            "region": "europe-west1",
            "unit": "h",
            "unit_price": 0.0520,
            "sku_group": "CPU",
            "description": "N2 Instance Core running in Europe",
        },
        # SSD Persistent Disk in us-central1
        {
            "sku_id": "SKU-SSD-USC1",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.1700,
            "sku_group": "SSD",
            "description": "SSDBacked PD Capacity",
        },
        # Standard Persistent Disk in us-central1
        {
            "sku_id": "SKU-PD-USC1",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0400,
            "sku_group": "PDStandard",
            "description": "Storage PD Capacity",
        },
    ]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_machine_type_specs_resolved() -> None:
    """Verify that standard GCE machine types resolve to correct vCPU/RAM specs."""
    vcpu, ram = resolve_machine_type_specs("n2-standard-4")
    assert vcpu == 4
    assert ram == 16.0

    vcpu, ram = resolve_machine_type_specs("custom-8-32768")
    assert vcpu == 8
    assert ram == 32.0

    # Unrecognized returns (0, 0.0)
    vcpu, ram = resolve_machine_type_specs("unknown-type-name")
    assert vcpu == 0
    assert ram == 0.0


def test_gce_instance_maps_to_vcpu_and_ram_skus(populated_db: str) -> None:
    """Verify that a GCE instance decomposes into vCPU and RAM cached SKUs."""
    resource = Resource(
        provider="gcp",
        resource_id="vm-1",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
    )

    mapper = GcpSkuMapper(populated_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 2

    # Check vcpu mapping
    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    assert vcpu_map["sku_id"] == "SKU-N2-CPU-USC1"
    assert vcpu_map["unit_price"] == 0.0475
    assert vcpu_map["unit"] == "h"
    assert vcpu_map["qty"] == 4.0  # 4 vCPUs

    # Check ram mapping
    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert ram_map["sku_id"] == "SKU-N2-RAM-USC1"
    assert ram_map["unit_price"] == 0.0063
    assert ram_map["unit"] == "GiBy.mo"
    assert ram_map["qty"] == 16.0  # 16 GB RAM


def test_region_specific_price_selected(populated_db: str) -> None:
    """Verify that mapping selects prices matching the resource's region."""
    resource = Resource(
        provider="gcp",
        resource_id="vm-2",
        service="compute",
        kind="gce_instance",
        region="europe-west1",
        attributes={"machine_type": "n2-standard-4"},
    )

    mapper = GcpSkuMapper(populated_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    # Europe has no RAM SKU in our populated_db, so RAM is unpriced, but CPU should map to Europe
    assert len(unpriced) == 1
    assert unpriced[0]["reason"] == "No matching RAM SKU found in region europe-west1"

    assert len(mappings) == 1
    assert mappings[0]["component"] == "vcpu"
    assert mappings[0]["sku_id"] == "SKU-N2-CPU-EUW1"
    assert mappings[0]["unit_price"] == 0.0520


def test_attached_ssd_disk_maps_to_disk_sku(populated_db: str) -> None:
    """Verify that attached SSD persistent disks map to the SSD storage SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="vm-1",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
        attached=[
            AttachedResource(
                kind="ssd_persistent_disk",
                quantity=1,
                attributes={"size_gb": 100},
            )
        ],
    )

    mapper = GcpSkuMapper(populated_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 3  # CPU + RAM + Disk

    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-SSD-USC1"
    assert disk_map["unit_price"] == 0.1700
    assert disk_map["unit"] == "GiBy.mo"
    assert disk_map["qty"] == 100.0  # 100 GB


def test_attached_standard_disk_maps_to_disk_sku(populated_db: str) -> None:
    """Verify that attached Standard persistent disks map to the standard storage SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="vm-1",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
        attached=[
            AttachedResource(
                kind="pd_persistent_disk",
                quantity=1,
                attributes={"size_gb": 100},
            )
        ],
    )

    mapper = GcpSkuMapper(populated_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    assert len(mappings) == 3  # CPU + RAM + Disk

    disk_map = next(m for m in mappings if m["component"] == "storage")
    assert disk_map["sku_id"] == "SKU-PD-USC1"
    assert disk_map["unit_price"] == 0.0400
    assert disk_map["unit"] == "GiBy.mo"
    assert disk_map["qty"] == 100.0  # 100 GB


def test_unmappable_resource_reported_unpriced(populated_db: str) -> None:
    """Verify that unrecognized services/kinds are flagged in the unpriced list."""
    resource = Resource(
        provider="gcp",
        resource_id="other-1",
        service="unknown",
        kind="unsupported_kind",
        region="us-central1",
    )

    mapper = GcpSkuMapper(populated_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "unsupported resource kind" in unpriced[0]["reason"].lower()
