# SPDX-License-Identifier: Apache-2.0

from typing import Any, Callable, List


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
        assumptions: List[str],
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
