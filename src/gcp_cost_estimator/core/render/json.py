# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.estimate import Estimate
from gcp_cost_estimator.core.registries import OutputRenderer, register_output_renderer


class JsonRenderer(OutputRenderer):
    """Renders estimates as formatted JSON strings."""

    def render(self, estimate: Estimate) -> str:
        return estimate.model_dump_json(indent=2)


register_output_renderer("json", JsonRenderer)
