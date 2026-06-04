import pytest
from pydantic import ValidationError

# We expect this import to fail initially (Red step)
from gcp_billing_mcp.core.model import (
    ResourceModel,
    get_resource_model_schema,
)


def test_valid_minimal_resource_parses() -> None:
    """Verify that a valid minimal resource successfully parses."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
            }
        ]
    }
    model = ResourceModel(**data)
    assert len(model.resources) == 1
    assert model.resources[0].provider == "gcp"
    assert model.resources[0].resource_id == "vm-1"
    assert model.resources[0].quantity == 1  # default value


def test_unknown_top_level_field_rejected() -> None:
    """Verify that unknown top-level fields are rejected by Pydantic."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "unknown_field_xyz": "value",
            }
        ]
    }
    with pytest.raises(ValidationError):
        ResourceModel(**data)


def test_provider_specifics_go_in_attributes() -> None:
    """Verify that provider specifics go into attributes, not root."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "attributes": {"machine_type": "n2-standard-4", "preemptible": True},
            }
        ]
    }
    model = ResourceModel(**data)
    assert model.resources[0].attributes["machine_type"] == "n2-standard-4"
    assert model.resources[0].attributes["preemptible"] is True


def test_attached_resources_and_quantity_round_trip() -> None:
    """Verify attached resources and quantities parse and roundtrip correctly."""
    data = {
        "resources": [
            {
                "provider": "gcp",
                "resource_id": "vm-1",
                "service": "compute",
                "kind": "gce_instance",
                "quantity": 3,
                "attached": [
                    {
                        "kind": "ssd_persistent_disk",
                        "quantity": 2,
                        "attributes": {"size_gb": 100},
                    }
                ],
            }
        ]
    }
    model = ResourceModel(**data)
    assert model.resources[0].quantity == 3
    assert len(model.resources[0].attached) == 1
    assert model.resources[0].attached[0].kind == "ssd_persistent_disk"
    assert model.resources[0].attached[0].quantity == 2
    assert model.resources[0].attached[0].attributes["size_gb"] == 100


def test_schema_export_matches_model() -> None:
    """Verify schema export produces a valid dictionary matching Pydantic structure."""
    schema = get_resource_model_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "resources" in schema["properties"]
