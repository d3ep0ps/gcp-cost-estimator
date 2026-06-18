# SPDX-License-Identifier: Apache-2.0

from typing import Any, Callable

from gcp_cost_estimator.core.model import Resource
from gcp_cost_estimator.core.iac.gcp.context import ParserContext

ParserFunc = Callable[[str, ParserContext, dict[str, str]], Resource]

RESOURCE_TYPE_MAP: dict[str, ParserFunc] = {}
