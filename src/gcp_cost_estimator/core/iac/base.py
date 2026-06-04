# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from typing import Any

from gcp_cost_estimator.core.model import ResourceModel


class IaCParser(ABC):
    """Abstract base class for Infrastructure as Code (IaC) parsers."""

    @abstractmethod
    def parse(self, path: str, options: dict[str, Any] | None = None) -> ResourceModel:
        """Parse IaC files or directory and return a canonical ResourceModel."""
        pass


# Global registry of IaCParsers
_IAC_PARSERS: dict[str, type[IaCParser]] = {}


def register_iac_parser(format_name: str, parser_class: type[IaCParser]) -> None:
    """Register a concrete IaCParser implementation."""
    _IAC_PARSERS[format_name.lower()] = parser_class


def get_iac_parser(format_name: str) -> IaCParser:
    """Retrieve and instantiate the IaCParser for a format."""
    parser_class = _IAC_PARSERS.get(format_name.lower())
    if not parser_class:
        msg = f"No IaCParser registered for format '{format_name}'"
        raise ValueError(msg)
    return parser_class()
