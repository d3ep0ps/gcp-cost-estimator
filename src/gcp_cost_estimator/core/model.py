# SPDX-License-Identifier: Apache-2.0

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttachedResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    quantity: int = 1
    attributes: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    resource_id: str
    service: str
    kind: str
    region: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    attached: list[AttachedResource] = Field(default_factory=list)
    quantity: int = 1
    assumptions: list[str] = Field(default_factory=list)


class ResourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resources: list[Resource]


def get_resource_model_schema() -> dict[str, Any]:
    """Return the JSON Schema for the ResourceModel."""
    return ResourceModel.model_json_schema()
