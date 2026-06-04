from abc import ABC, abstractmethod
from typing import Any

from gcp_billing_mcp.core.estimate import Estimate
from gcp_billing_mcp.core.model import Resource


class SkuMapper(ABC):
    """Abstract base class for cloud provider SKU mapping logic."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    @classmethod
    def get_supported_billing_services(cls) -> list[str]:
        """Return the list of official billing service display names required by this provider."""
        return []

    @abstractmethod
    def map_resource_to_skus(
        self, resource: Resource
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Decompose resource into priced SKU mappings and unpriced items.

        Returns a tuple of:
          - mappings: List[Dict[str, Any]] containing:
              - sku_id, component, unit_price, unit, qty
          - unpriced: List[Dict[str, Any]] containing:
              - resource_id, reason
        """
        pass


# Global registry of SkuMappers
_SKU_MAPPERS: dict[str, type[SkuMapper]] = {}


def register_sku_mapper(provider: str, mapper_class: type[SkuMapper]) -> None:
    """Register a concrete SkuMapper implementation for a provider."""
    _SKU_MAPPERS[provider.lower()] = mapper_class


def get_sku_mapper_class(provider: str) -> type[SkuMapper] | None:
    """Retrieve the SkuMapper class for a provider without instantiating it."""
    return _SKU_MAPPERS.get(provider.lower())


def get_sku_mapper(provider: str, db_path: str) -> SkuMapper:
    """Retrieve and instantiate the SkuMapper for a provider."""
    mapper_class = get_sku_mapper_class(provider)
    if not mapper_class:
        raise ValueError(f"No SkuMapper registered for provider '{provider}'")
    return mapper_class(db_path)


class OutputRenderer(ABC):
    """Abstract base class for formatting cost estimates."""

    @abstractmethod
    def render(self, estimate: Estimate) -> str:
        """Format the estimate to a string format."""
        pass


# Global registry of OutputRenderers
_OUTPUT_RENDERERS: dict[str, type[OutputRenderer]] = {}


def register_output_renderer(format_name: str, renderer_class: type[OutputRenderer]) -> None:
    """Register a concrete OutputRenderer implementation."""
    _OUTPUT_RENDERERS[format_name.lower()] = renderer_class


def get_output_renderer(format_name: str) -> OutputRenderer:
    """Retrieve and instantiate the OutputRenderer for a format."""
    renderer_class = _OUTPUT_RENDERERS.get(format_name.lower())
    if not renderer_class:
        msg = f"No OutputRenderer registered for format '{format_name}'"
        raise ValueError(msg)
    return renderer_class()
