# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable
from typing import Any


class ParserContext:
    """Shared parsing context for extracting resource attributes in GCP IaC mappers.

    This abstracts differences between Terraform HCL and plan JSON formats by:
    - Wrapping raw attributes (e.g., res_config in HCL, values in plan JSON)
    - Handling value resolution (variable lookup in HCL, identity in plan JSON)
    - Appending warning/assumption logs when unresolved variables or fallbacks occur
    """

    def __init__(
        self,
        attrs: dict[str, Any],
        resolve: Callable[[Any], Any],
        is_unresolved: Callable[[Any], bool],
        assumptions: list[str],
    ):
        self.attrs = attrs
        self._resolve = resolve
        self._is_unresolved = is_unresolved
        self.assumptions = assumptions

    def get(self, key: str, default: Any = None) -> Any:
        """Get an attribute key, applying value resolution."""
        return self._resolve(self.attrs.get(key, default))

    def resolve(self, val: Any) -> Any:
        """Resolve a value directly (e.g. from sub-attributes/lists)."""
        return self._resolve(val)

    def is_unresolved(self, val: Any) -> bool:
        """Check if a value contains unresolved Terraform variables."""
        return self._is_unresolved(val)

    def add_assumption(self, msg: str) -> None:
        """Add an estimation assumption for this resource."""
        if msg not in self.assumptions:
            self.assumptions.append(msg)

    def extract_region(self) -> str | None:
        """Extract region from zone, region, or location attributes."""
        raw_zone = self.get("zone")
        raw_region = self.get("region")
        raw_location = self.get("location")

        if raw_zone and isinstance(raw_zone, str):
            if self.is_unresolved(raw_zone):
                self.add_assumption(f"Unresolved zone reference: '{raw_zone}'")
            else:
                parts = raw_zone.split("-")
                if len(parts) >= 2:
                    return "-".join(parts[:-1])
        elif raw_region and isinstance(raw_region, str):
            if self.is_unresolved(raw_region):
                self.add_assumption(f"Unresolved region reference: '{raw_region}'")
            else:
                return raw_region
        elif raw_location and isinstance(raw_location, str):
            if self.is_unresolved(raw_location):
                self.add_assumption(f"Unresolved region reference: '{raw_location}'")
            else:
                return raw_location
        return None

    def extract_quantity(self) -> int:
        """Extract resource count/quantity from the count attribute."""
        quantity = 1
        raw_count = self.get("count")
        if raw_count is not None:
            if self.is_unresolved(raw_count):
                self.add_assumption(
                    "Unresolved count variable reference: default to quantity 1. "
                    f"Count reference: '{raw_count}'"
                )
            else:
                try:
                    quantity = int(raw_count)
                except (ValueError, TypeError):
                    self.add_assumption(
                        f"Invalid count value '{raw_count}': default to quantity 1."
                    )
        return quantity
