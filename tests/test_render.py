# SPDX-License-Identifier: Apache-2.0

import csv
import io
import json

import pytest

from gcp_billing_mcp.core.estimate import Estimate, PricedLineItem, UnpricedItem
from gcp_billing_mcp.core.registries import get_output_renderer


@pytest.fixture
def sample_estimate() -> Estimate:
    """Fixture providing a mock Estimate for rendering tests."""
    return Estimate(
        pricing_snapshot="2026-06-03T12:00:00Z",
        line_items=[
            PricedLineItem(
                resource_id="google_compute_instance.vm_instance",
                sku_id="SKU-CPU",
                component="vcpu",
                unit_price=0.0475,
                unit="h",
                qty=4.0,
                usage_hours=730.0,
                monthly_cost=138.7,
            ),
            PricedLineItem(
                resource_id="google_compute_instance.vm_instance",
                sku_id="SKU-RAM",
                component="ram",
                unit_price=0.0063,
                unit="GiBy.mo",
                qty=16.0,
                usage_hours=730.0,
                monthly_cost=0.1,
            ),
        ],
        monthly_total=138.8,
        unpriced=[
            UnpricedItem(
                resource_id="google_pubsub_topic.topic", reason="Unsupported resource kind"
            )
        ],
        assumptions=["Defaulted runtime to 730 hours"],
    )


def test_json_renderer_roundtrips(sample_estimate) -> None:
    """Verifies that the JSON renderer formats estimates into parseable JSON."""
    renderer = get_output_renderer("json")
    output = renderer.render(sample_estimate)

    assert isinstance(output, str)
    data = json.loads(output)
    assert data["monthly_total"] == 138.8
    assert len(data["line_items"]) == 2
    assert data["line_items"][0]["sku_id"] == "SKU-CPU"
    assert data["unpriced"][0]["resource_id"] == "google_pubsub_topic.topic"


def test_csv_has_header_and_one_row_per_line_item(sample_estimate) -> None:
    """Verifies that the CSV renderer outputs correct headers and line item values."""
    renderer = get_output_renderer("csv")
    output = renderer.render(sample_estimate)

    assert isinstance(output, str)
    f = io.StringIO(output)
    reader = csv.DictReader(f)

    # Assert correct header columns
    expected_headers = [
        "resource_id",
        "sku_id",
        "component",
        "unit_price",
        "unit",
        "qty",
        "monthly_cost",
    ]
    assert reader.fieldnames == expected_headers

    rows = list(reader)
    assert len(rows) == 2

    # Check values on first row
    row0 = rows[0]
    assert row0["resource_id"] == "google_compute_instance.vm_instance"
    assert row0["sku_id"] == "SKU-CPU"
    assert float(row0["monthly_cost"]) == 138.7


def test_markdown_table_includes_total_and_disclaimer(sample_estimate) -> None:
    """Verifies that the Markdown renderer produces a structured markdown table with totals."""
    renderer = get_output_renderer("markdown")
    output = renderer.render(sample_estimate)

    assert isinstance(output, str)
    assert "2026-06-03T12:00:00Z" in output
    assert "list price only" in output.lower()
    assert "138.8" in output
    assert "google_pubsub_topic.topic" in output
    assert "Unsupported resource kind" in output
    assert "Defaulted runtime to 730 hours" in output


def test_unknown_format_raises() -> None:
    """Verifies that requesting an unregistered renderer format raises ValueError."""
    with pytest.raises(ValueError, match="No OutputRenderer registered"):
        get_output_renderer("xlsx")
