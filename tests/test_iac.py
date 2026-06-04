# SPDX-License-Identifier: Apache-2.0

import json

from gcp_billing_mcp.core.iac.base import get_iac_parser
from gcp_billing_mcp.core.iac.terraform_plan import parse_terraform
from gcp_billing_mcp.core.model import ResourceModel


def test_hcl_parses_single_gce_instance(tmp_path) -> None:
    """Verifies that static HCL parsing correctly extracts a GCE VM resource."""
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      name         = "terraform-instance"
      machine_type = "n2-standard-4"
      zone         = "us-central1-a"
      boot_disk {
        initialize_params {
          image = "debian-cloud/debian-11"
          size  = 50
          type  = "pd-ssd"
        }
      }
    }
    """
    # Write HCL to a temporary file in tmp_path
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert isinstance(model, ResourceModel)
    assert len(model.resources) == 1

    resource = model.resources[0]
    assert resource.provider == "gcp"
    assert resource.resource_id == "google_compute_instance.vm_instance"
    assert resource.service == "compute"
    assert resource.kind == "gce_instance"
    assert resource.region == "us-central1"
    assert resource.attributes.get("machine_type") == "n2-standard-4"

    assert len(resource.attached) == 1
    attached = resource.attached[0]
    assert attached.kind == "ssd_persistent_disk"
    assert attached.attributes.get("size_gb") == 50


def test_hcl_unresolved_count_var_flagged_not_assumed(tmp_path) -> None:
    """Verifies that HCL parser flags unresolved counts and variable references."""
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      count        = var.undefined_count
      name         = "instance-${count.index}"
      machine_type = var.my_machine_type
      zone         = "us-central1-a"
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    resource = model.resources[0]
    # Counts that aren't resolvable should default to 1, but be flagged in assumptions
    assert resource.quantity == 1

    assert any("count" in a.lower() for a in resource.assumptions)

    # machine_type is unresolved variable reference, should retain placeholder representation
    assert "my_machine_type" in resource.attributes.get("machine_type", "")
    assert any(
        "my_machine_type" in a.lower() or "unresolved" in a.lower() for a in resource.assumptions
    )


def test_unsupported_resource_type_reported(tmp_path) -> None:
    """Verifies that unsupported resources are mapped to placeholder GCP resources.

    This allows Downstream SkuMapper to flag them as unpriced.
    """
    hcl_content = """
    resource "google_pubsub_topic" "topic" {
      name = "my-topic"
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    resource = model.resources[0]
    assert resource.provider == "gcp"
    assert resource.resource_id == "google_pubsub_topic.topic"
    assert resource.service == "pubsub"
    assert resource.kind == "google_pubsub_topic"


def test_plan_json_resolves_count_and_vars(tmp_path) -> None:
    """Verifies that Terraform Plan JSON parsing resolves dynamic counts and variables."""
    # Mimic a simple portion of terraform show -json output
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "google_compute_instance.vm_instance[0]",
                        "mode": "managed",
                        "type": "google_compute_instance",
                        "name": "vm_instance",
                        "index": 0,
                        "provider_name": "registry.terraform.io/hashicorp/google",
                        "values": {
                            "name": "instance-0",
                            "machine_type": "n2-standard-4",
                            "zone": "us-central1-a",
                            "boot_disk": [{"initialize_params": [{"size": 100, "type": "pd-ssd"}]}],
                        },
                    },
                    {
                        "address": "google_compute_instance.vm_instance[1]",
                        "mode": "managed",
                        "type": "google_compute_instance",
                        "name": "vm_instance",
                        "index": 1,
                        "provider_name": "registry.terraform.io/hashicorp/google",
                        "values": {
                            "name": "instance-1",
                            "machine_type": "n2-standard-4",
                            "zone": "us-central1-a",
                            "boot_disk": [{"initialize_params": [{"size": 100, "type": "pd-ssd"}]}],
                        },
                    },
                ]
            }
        },
    }

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan_data))

    # Test parse_terraform directly in plan mode
    model = parse_terraform(str(plan_file), mode="plan")

    # The parser should find resources in plan JSON. If there are multiple resources
    # of the same type (like multiple VMs from count or for_each), we represent
    # them as individual Resource objects with their own addresses.
    # This matches standard Terraform resource address behavior.
    assert len(model.resources) == 2
    for r in model.resources:
        assert r.provider == "gcp"
        assert "google_compute_instance.vm_instance" in r.resource_id
        assert r.attributes.get("machine_type") == "n2-standard-4"
        assert r.region == "us-central1"
        assert len(r.attached) == 1
        assert r.attached[0].kind == "ssd_persistent_disk"
        assert r.attached[0].attributes.get("size_gb") == 100


def test_plan_json_maps_modules(tmp_path) -> None:
    """Verifies that resources nested inside child modules in plan JSON are discovered."""
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "child_modules": [
                    {
                        "resources": [
                            {
                                "address": "module.my_module.google_compute_instance.vm_instance",
                                "mode": "managed",
                                "type": "google_compute_instance",
                                "name": "vm_instance",
                                "provider_name": "registry.terraform.io/hashicorp/google",
                                "values": {
                                    "name": "module-instance",
                                    "machine_type": "e2-medium",
                                    "zone": "europe-west1-b",
                                    "boot_disk": [],
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
    resource = model.resources[0]
    assert resource.resource_id == "module.my_module.google_compute_instance.vm_instance"
    assert resource.attributes.get("machine_type") == "e2-medium"
    assert resource.region == "europe-west1"


def test_auto_mode_prefers_plan_falls_back_to_hcl(tmp_path) -> None:
    """Verifies auto mode: plan JSON files are parsed as plans, directories are parsed as HCL."""
    # Write HCL to directory
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      name         = "terraform-instance"
      machine_type = "e2-standard-2"
      zone         = "us-central1-b"
    }
    """
    (tmp_path / "main.tf").write_text(hcl_content)

    # Test parsing the directory (should auto-detect HCL)
    model_dir = parse_terraform(str(tmp_path), mode="auto")
    assert len(model_dir.resources) == 1
    assert model_dir.resources[0].attributes.get("machine_type") == "e2-standard-2"

    # Write a plan.json to another path
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "google_compute_instance.vm_instance",
                        "mode": "managed",
                        "type": "google_compute_instance",
                        "name": "vm_instance",
                        "provider_name": "registry.terraform.io/hashicorp/google",
                        "values": {
                            "name": "plan-instance",
                            "machine_type": "n1-standard-8",
                            "zone": "us-central1-c",
                        },
                    }
                ]
            }
        },
    }
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan_data))

    # Test parsing the file (should auto-detect plan JSON)
    model_file = parse_terraform(str(plan_file), mode="auto")
    assert len(model_file.resources) == 1
    assert model_file.resources[0].attributes.get("machine_type") == "n1-standard-8"


def test_hcl_default_machine_type(tmp_path) -> None:
    """Verifies that missing machine_type defaults to e2-medium."""
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      name         = "terraform-instance"
      zone         = "us-central1-a"
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    assert model.resources[0].attributes.get("machine_type") == "e2-medium"
    assert any("fallback to e2-medium" in a for a in model.resources[0].assumptions)


def test_hcl_count_integer(tmp_path) -> None:
    """Verifies HCL count defined as an integer parses correctly."""
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      count        = 3
      name         = "instance-${count.index}"
      machine_type = "n2-standard-4"
      zone         = "us-central1-a"
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    assert model.resources[0].quantity == 3


def test_hcl_invalid_boot_disk_size(tmp_path) -> None:
    """Verifies that invalid boot disk size defaults safely and logs an assumption."""
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      name         = "terraform-instance"
      machine_type = "n2-standard-4"
      zone         = "us-central1-a"
      boot_disk {
        initialize_params {
          size = "invalid-size"
        }
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    resource = model.resources[0]
    assert len(resource.attached) == 1
    assert resource.attached[0].attributes.get("size_gb") == 10
    assert any("invalid boot disk size" in a for a in resource.assumptions)


def test_hcl_malformed_boot_disk(tmp_path) -> None:
    """Verifies that malformed boot_disk configurations are safely skipped."""
    hcl_content = """
    resource "google_compute_instance" "vm_instance" {
      name         = "terraform-instance"
      machine_type = "n2-standard-4"
      zone         = "us-central1-a"
      boot_disk    = ["not-a-dict"]
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    assert len(model.resources[0].attached) == 0


def test_hcl_preemptible_vm(tmp_path) -> None:
    """Verifies that the HCL parser extracts the preemptible flag from scheduling block."""
    hcl_content = """
    resource "google_compute_instance" "spot_worker" {
      name         = "spot-worker"
      machine_type = "n2-standard-4"
      zone         = "us-central1-a"

      scheduling {
        preemptible       = true
        automatic_restart = false
      }
    }
    """
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(hcl_content)

    parser = get_iac_parser("terraform")
    model = parser.parse(str(tmp_path))

    assert len(model.resources) == 1
    assert model.resources[0].attributes.get("preemptible") is True


def test_plan_json_preemptible_vm(tmp_path) -> None:
    """Verifies that the Plan JSON parser extracts the preemptible flag from scheduling block."""
    plan_data = {
        "format_version": "1.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "google_compute_instance.spot_worker",
                        "mode": "managed",
                        "type": "google_compute_instance",
                        "name": "spot_worker",
                        "provider_name": "registry.terraform.io/hashicorp/google",
                        "values": {
                            "name": "spot-worker",
                            "machine_type": "n2-standard-4",
                            "zone": "us-central1-a",
                            "scheduling": [
                                {
                                    "preemptible": True,
                                    "automatic_restart": False,
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
    assert model.resources[0].attributes.get("preemptible") is True
