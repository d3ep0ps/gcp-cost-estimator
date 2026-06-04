from gcp_billing_mcp.core.iac.terraform_hcl import TerraformHclParser
from gcp_billing_mcp.core.iac.terraform_plan import TerraformPlanParser, parse_terraform


def test_hcl_parses_google_container_cluster_minimal() -> None:
    """Verify that a minimal GKE cluster parses location as region."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_container_cluster.minimal")
    assert res.provider == "gcp"
    assert res.service == "container"
    assert res.kind == "gke_cluster"
    assert res.region == "us-central1"


def test_hcl_parses_google_container_cluster_with_node_config() -> None:
    """Verify GKE cluster with explicit node_config parses correctly."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_container_cluster.with_node_config"
    )
    assert res.provider == "gcp"
    assert res.service == "container"
    assert res.kind == "gke_cluster"
    assert res.region == "us-central1"
    assert res.attributes["node_count"] == 3
    assert res.attributes["machine_type"] == "e2-standard-4"
    assert res.attributes["disk_size_gb"] == 100
    assert res.attributes["disk_type"] == "pd-standard"


def test_hcl_parses_google_container_node_pool() -> None:
    """Verify standalone GKE node pool HCL parses correctly."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(r for r in model.resources if r.resource_id == "google_container_node_pool.pool")
    assert res.provider == "gcp"
    assert res.service == "container"
    assert res.kind == "gke_node_pool"
    assert res.region == "us-central1"
    assert res.attributes["node_count"] == 2
    assert res.attributes["machine_type"] == "e2-standard-4"
    assert res.attributes["disk_size_gb"] == 100
    assert res.attributes["disk_type"] == "pd-ssd"


def test_hcl_gke_unresolved_node_count_flagged() -> None:
    """Verify unresolved node count in HCL cluster gets flagged in assumptions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_container_cluster.unresolved_nodes"
    )
    assert any("Unresolved attribute node_count" in a for a in res.assumptions)


def test_hcl_gke_unresolved_machine_type_flagged() -> None:
    """Verify unresolved machine type in HCL cluster gets flagged in assumptions."""
    parser = TerraformHclParser()
    model = parser.parse("tests/fixtures/terraform")

    res = next(
        r for r in model.resources if r.resource_id == "google_container_cluster.unresolved_mtype"
    )
    assert any("Unresolved attribute machine_type" in a for a in res.assumptions)


def test_plan_json_resolves_google_container_cluster() -> None:
    """Verify GKE cluster parses correctly from plan JSON."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/gke_plan.json")

    res = next(r for r in model.resources if r.resource_id == "google_container_cluster.primary")
    assert res.provider == "gcp"
    assert res.service == "container"
    assert res.kind == "gke_cluster"
    assert res.region == "us-central1"
    assert res.attributes["node_count"] == 3
    assert res.attributes["machine_type"] == "e2-standard-4"
    assert res.attributes["disk_size_gb"] == 100
    assert res.attributes["disk_type"] == "pd-standard"


def test_plan_json_resolves_google_container_node_pool() -> None:
    """Verify GKE node pool parses correctly from plan JSON."""
    parser = TerraformPlanParser()
    model = parser.parse("tests/fixtures/terraform/gke_plan.json")

    res = next(
        r for r in model.resources if r.resource_id == "google_container_node_pool.extra_pool"
    )
    assert res.provider == "gcp"
    assert res.service == "container"
    assert res.kind == "gke_node_pool"
    assert res.region == "us-central1"
    assert res.attributes["node_count"] == 2
    assert res.attributes["machine_type"] == "e2-standard-4"
    assert res.attributes["disk_size_gb"] == 100
    assert res.attributes["disk_type"] == "pd-ssd"


def test_auto_mode_parses_both_cluster_and_node_pool() -> None:
    """Verify parse_terraform in auto mode parses GKE plan JSON successfully."""
    model = parse_terraform("tests/fixtures/terraform/gke_plan.json")

    cluster = next(
        r for r in model.resources if r.resource_id == "google_container_cluster.primary"
    )
    assert cluster.kind == "gke_cluster"

    pool = next(
        r for r in model.resources if r.resource_id == "google_container_node_pool.extra_pool"
    )
    assert pool.kind == "gke_node_pool"
