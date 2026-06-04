# SPDX-License-Identifier: Apache-2.0

import json
import sqlite3
from pathlib import Path

import pytest

from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper


@pytest.fixture
def populated_gcs_db(temp_db_path: str) -> str:
    """Pre-populate a temporary cache database with static GCS SKU fixtures."""
    conn = sqlite3.connect(temp_db_path)
    init_db(conn)
    conn.close()

    with Path("tests/fixtures/gcs_skus.json").open() as f:
        mock_skus = json.load(f)

    # Filter out the metadata item
    mock_skus = [s for s in mock_skus if s["sku_id"] != "METADATA-CITATION"]

    update_cache(temp_db_path, "gcp", mock_skus, "2026-06-03T12:00:00Z")
    return temp_db_path


def test_gcs_standard_storage_maps_to_storage_sku(populated_gcs_db: str) -> None:
    """Verify that a standard storage bucket maps to the standard storage SKU."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-1",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 100.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Emits standard storage, Class A ops, Class B ops, Egress (due to default values normalized, but here we pass usage directly)
    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "GCS-STANDARD-STORAGE-US-CENTRAL1"
    assert storage_map["qty"] == 100.0


def test_gcs_nearline_storage_maps_to_nearline_sku(populated_gcs_db: str) -> None:
    """Verify Nearline storage mapping."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-2",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "NEARLINE"},
        usage={"size_gb": 150.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "GCS-NEARLINE-STORAGE-US-CENTRAL1"
    assert storage_map["qty"] == 150.0


def test_gcs_coldline_storage_maps_to_coldline_sku(populated_gcs_db: str) -> None:
    """Verify Coldline storage mapping."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-3",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "COLDLINE"},
        usage={"size_gb": 200.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "GCS-COLDLINE-STORAGE-US-CENTRAL1"
    assert storage_map["qty"] == 200.0


def test_gcs_archive_storage_maps_to_archive_sku(populated_gcs_db: str) -> None:
    """Verify Archive storage mapping."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-4",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "ARCHIVE"},
        usage={"size_gb": 250.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "GCS-ARCHIVE-STORAGE-US-CENTRAL1"
    assert storage_map["qty"] == 250.0


def test_gcs_class_a_ops_mapped_when_nonzero(populated_gcs_db: str) -> None:
    """Verify Class A operations SKU is mapped when usage is non-zero."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-5",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 0.0, "monthly_class_a_ops": 20000.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    ops_map = next(m for m in mappings if m["component"] == "class_a_ops")
    assert ops_map["sku_id"] == "GCS-CLASS-A-OPS-STANDARD"
    # Quantity is per 10k operations: 20000 / 10000 = 2.0
    assert ops_map["qty"] == 2.0


def test_gcs_class_b_ops_mapped_when_nonzero(populated_gcs_db: str) -> None:
    """Verify Class B operations SKU is mapped when usage is non-zero."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-6",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 0.0, "monthly_class_b_ops": 50000.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    ops_map = next(m for m in mappings if m["component"] == "class_b_ops")
    assert ops_map["sku_id"] == "GCS-CLASS-B-OPS-STANDARD"
    # Quantity is per 10k operations: 50000 / 10000 = 5.0
    assert ops_map["qty"] == 5.0


def test_gcs_ops_not_emitted_when_zero(populated_gcs_db: str) -> None:
    """Verify operations SKUs are not emitted when usage is zero."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-7",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 100.0, "monthly_class_a_ops": 0.0, "monthly_class_b_ops": 0.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Only storage should be emitted
    assert len(mappings) == 1
    assert mappings[0]["component"] == "storage"


def test_gcs_egress_mapped_when_nonzero(populated_gcs_db: str) -> None:
    """Verify internet egress SKU is mapped when egress is non-zero."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-8",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 0.0, "monthly_egress_gb": 50.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    egress_map = next(m for m in mappings if m["component"] == "egress")
    assert egress_map["sku_id"] == "GCS-INTERNET-EGRESS-STANDARD"
    assert egress_map["qty"] == 50.0


def test_gcs_retrieval_fee_emitted_for_nearline(populated_gcs_db: str) -> None:
    """Verify retrieval fee is emitted when retrieval usage is non-zero for cold class (Nearline)."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-9",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "NEARLINE"},
        usage={"size_gb": 0.0, "monthly_retrieval_gb": 30.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    retrieval_map = next(m for m in mappings if m["component"] == "retrieval")
    assert retrieval_map["sku_id"] == "GCS-RETRIEVAL-NEARLINE"
    assert retrieval_map["qty"] == 30.0


def test_gcs_retrieval_fee_not_emitted_for_standard(populated_gcs_db: str) -> None:
    """Verify retrieval fee is NOT emitted (reported as unpriced or omitted) for STANDARD storage."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-10",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 0.0, "monthly_retrieval_gb": 30.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    # Standard does not have retrieval fee SKU, so it should not be emitted
    retrieval_maps = [m for m in mappings if m["component"] == "retrieval"]
    assert len(retrieval_maps) == 0


def test_gcs_unknown_storage_class_reported_unpriced(populated_gcs_db: str) -> None:
    """Verify unknown storage class is reported as unpriced if mapping fails."""
    # (Note: validate.py falls back unrecognized storage classes to STANDARD,
    # but we test direct mapper response to verify robustness)
    resource = Resource(
        provider="gcp",
        resource_id="bucket-11",
        service="storage",
        kind="gcs_bucket",
        region="us-central1",
        attributes={"storage_class": "UNKNOWNCLASS"},
        usage={"size_gb": 100.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(mappings) == 0
    assert len(unpriced) == 1
    assert "storage class" in unpriced[0]["reason"].lower()


def test_gcs_region_specific_sku_selected(populated_gcs_db: str) -> None:
    """Verify region/location type specific storage SKU is selected (US multi-region)."""
    resource = Resource(
        provider="gcp",
        resource_id="bucket-12",
        service="storage",
        kind="gcs_bucket",
        region="us",
        attributes={"storage_class": "STANDARD"},
        usage={"size_gb": 100.0},
    )
    mapper = GcpSkuMapper(populated_gcs_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert len(unpriced) == 0
    storage_map = next(m for m in mappings if m["component"] == "storage")
    assert storage_map["sku_id"] == "GCS-STANDARD-STORAGE-US"
