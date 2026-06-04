from gcp_billing_mcp.core.estimate import Estimate
from gcp_billing_mcp.core.registries import OutputRenderer, register_output_renderer


class MarkdownRenderer(OutputRenderer):
    """Renders estimates as human-readable Markdown tables."""

    def render(self, estimate: Estimate) -> str:
        lines = [
            "# Infrastructure Cost Estimate",
            "",
            f"* **Pricing Snapshot:** `{estimate.pricing_snapshot}`",
            "* **Disclaimer:** List price only. SUD/CUD/negotiated discounts NOT applied.",
            "",
            "## Cost Breakdown",
            "",
            "| Resource ID | Component | SKU ID | Price | Unit | Qty | Monthly Cost |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for item in estimate.line_items:
            price_str = f"${item.unit_price:.4f}"
            cost_str = f"${item.monthly_cost:.2f}"
            lines.append(
                f"| {item.resource_id} | {item.component} | {item.sku_id} | "
                f"{price_str} | {item.unit} | {item.qty:.2f} | {cost_str} |"
            )

        total_str = f"${estimate.monthly_total:.2f}"
        lines.append(f"| **TOTAL** | | | | | | **{total_str}** |")
        lines.append("")

        if estimate.unpriced:
            lines.append("## Unpriced Items")
            lines.append("")
            for up in estimate.unpriced:
                lines.append(f"* **{up.resource_id}**: {up.reason}")
            lines.append("")

        if estimate.assumptions:
            lines.append("## Assumptions")
            lines.append("")
            for a in estimate.assumptions:
                lines.append(f"* {a}")
            lines.append("")

        return "\n".join(lines)


register_output_renderer("markdown", MarkdownRenderer)
