import json

import pytest

from gcp_billing_mcp.mcp.server import mcp

pytestmark = pytest.mark.anyio


# --- Step P-1 Defaults Tests ---


async def test_defaults_resource_structured_and_parseable() -> None:
    """Verify that catalog://defaults returns a structured, parseable JSON dict."""
    contents = await mcp.read_resource("catalog://defaults")
    assert contents is not None
    assert len(contents) == 1

    # Try parsing as JSON (Step P-1 specifies the resource returns structured JSON)
    data = json.loads(contents[0].content)
    assert isinstance(data, dict)
    assert "compute" in data


async def test_defaults_resource_includes_cloud_storage_defaults() -> None:
    """Verify that catalog://defaults includes representative storage defaults."""
    contents = await mcp.read_resource("catalog://defaults")
    data = json.loads(contents[0].content)
    assert "storage" in data
    storage = data["storage"]
    assert storage["storage_class"]["value"] == "STANDARD"
    assert storage["size_gb"]["value"] == 100
    assert storage["monthly_class_a_ops"]["value"] == 10000
    assert storage["monthly_class_b_ops"]["value"] == 100000
    assert storage["monthly_egress_gb"]["value"] == 10
    assert storage["monthly_retrieval_gb"]["value"] == 0


async def test_defaults_resource_includes_gke_defaults() -> None:
    """Verify that catalog://defaults includes GKE defaults."""
    contents = await mcp.read_resource("catalog://defaults")
    data = json.loads(contents[0].content)
    assert "container" in data
    container = data["container"]
    assert container["node_count"]["value"] == 3
    assert container["machine_type"]["value"] == "e2-standard-4"
    assert container["disk_size_gb"]["value"] == 100
    assert container["disk_type"]["value"] == "pd-standard"
    assert container["runtime_hours_per_month"]["value"] == 730


async def test_defaults_resource_includes_bigquery_defaults() -> None:
    """Verify that catalog://defaults includes BigQuery defaults."""
    contents = await mcp.read_resource("catalog://defaults")
    data = json.loads(contents[0].content)
    assert "bigquery" in data
    bigquery = data["bigquery"]
    assert bigquery["active_storage_gb"]["value"] == 100
    assert bigquery["long_term_storage_gb"]["value"] == 0
    assert bigquery["monthly_query_tb"]["value"] == 1
    assert bigquery["monthly_streaming_gb"]["value"] == 0


async def test_defaults_resource_includes_cloud_sql_defaults() -> None:
    """Verify that catalog://defaults includes Cloud SQL defaults."""
    contents = await mcp.read_resource("catalog://defaults")
    data = json.loads(contents[0].content)
    assert "sql" in data
    sql = data["sql"]
    assert sql["runtime_hours_per_month"]["value"] == 730
    assert sql["disk_type"]["value"] == "PD_SSD"
    assert sql["availability_type"]["value"] == "ZONAL"
    assert sql["backup_enabled"]["value"] is False


# --- Step P-2 Coverage Tests ---


async def test_coverage_resource_is_valid_json() -> None:
    """Verify that catalog://coverage returns a structured, parseable JSON dict."""
    contents = await mcp.read_resource("catalog://coverage")
    assert contents is not None
    assert len(contents) == 1
    data = json.loads(contents[0].content)
    assert isinstance(data, dict)
    assert data["provider"] == "gcp"
    assert "services" in data


async def test_coverage_resource_contains_compute_gce_instance() -> None:
    """Verify compute engine coverage is present."""
    contents = await mcp.read_resource("catalog://coverage")
    data = json.loads(contents[0].content)
    services = data["services"]
    assert "compute" in services
    assert "gce_instance" in services["compute"]["kinds"]


async def test_coverage_resource_contains_sql_cloud_sql_instance() -> None:
    """Verify cloud sql coverage is present."""
    contents = await mcp.read_resource("catalog://coverage")
    data = json.loads(contents[0].content)
    services = data["services"]
    assert "sql" in services
    assert "cloud_sql_instance" in services["sql"]["kinds"]


async def test_coverage_resource_contains_storage() -> None:
    """Verify storage is present in the coverage dict."""
    contents = await mcp.read_resource("catalog://coverage")
    data = json.loads(contents[0].content)
    assert "storage" in data["services"]
    storage = data["services"]["storage"]
    assert "gcs_bucket" in storage["kinds"]
    assert "STANDARD" in storage["storage_classes"]


async def test_coverage_resource_contains_container() -> None:
    """Verify container/GKE is in the coverage dict."""
    contents = await mcp.read_resource("catalog://coverage")
    data = json.loads(contents[0].content)
    assert "container" in data["services"]
    container = data["services"]["container"]
    assert "gke_cluster" in container["kinds"]
    assert "gke_node_pool" in container["kinds"]


async def test_coverage_resource_contains_bigquery() -> None:
    """Verify bigquery is present in the coverage dict."""
    contents = await mcp.read_resource("catalog://coverage")
    data = json.loads(contents[0].content)
    assert "bigquery" in data["services"]
    bq = data["services"]["bigquery"]
    assert "bigquery_dataset" in bq["kinds"]
