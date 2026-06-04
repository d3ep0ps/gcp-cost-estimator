import csv
import io

from gcp_billing_mcp.core.estimate import Estimate
from gcp_billing_mcp.core.registries import OutputRenderer, register_output_renderer


class CsvRenderer(OutputRenderer):
    """Renders estimate line items as a CSV string."""

    def render(self, estimate: Estimate) -> str:
        output = io.StringIO()
        headers = [
            "resource_id",
            "sku_id",
            "component",
            "unit_price",
            "unit",
            "qty",
            "monthly_cost",
        ]
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
        writer.writeheader()

        for item in estimate.line_items:
            writer.writerow(
                {
                    "resource_id": item.resource_id,
                    "sku_id": item.sku_id,
                    "component": item.component,
                    "unit_price": item.unit_price,
                    "unit": item.unit,
                    "qty": item.qty,
                    "monthly_cost": item.monthly_cost,
                }
            )

        return output.getvalue()


register_output_renderer("csv", CsvRenderer)
