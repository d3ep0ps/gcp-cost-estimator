# SPDX-License-Identifier: Apache-2.0

import pytest

from gcp_cost_estimator.core.validation.utils import parse_k8s_quantity


@pytest.mark.parametrize(
    "val, expected",
    [
        # CPU: millicores → cores
        ("500m", "0.5"),
        ("1000m", "1"),
        ("250m", "0.25"),
        # CPU: plain numeric
        ("2", "2"),
        ("1.5", "1.5"),
        # unknown suffix — returned as-is
        ("4cpus", "4cpus"),
        # None and empty strings
        (None, ""),
        ("", ""),
        ("  ", ""),
    ],
)
def test_parse_k8s_quantity_cpu(val: object, expected: str) -> None:
    assert parse_k8s_quantity(val, is_cpu=True) == expected


@pytest.mark.parametrize(
    "val, expected",
    [
        # Binary suffixes (IEC)
        ("1Ki", "0"),  # 1024 bytes ≈ 0.000000953 GiB → rounds to "0" at 4dp
        ("512Mi", "0.5"),
        ("1Gi", "1.0"),
        ("2Gi", "2.0"),
        ("4Ti", "4096.0"),
        # Decimal suffixes (SI)
        ("1G", "0.9313"),  # 1e9 / 2^30 ≈ 0.9313
        ("1T", "931.3226"),  # 1e12 / 2^30 ≈ 931.32
        # Plain numeric (no suffix) — interpreted as bytes-like float GiB
        ("2", "2.0"),
        # Unknown suffix — returned as-is
        ("10Pb", "10Pb"),
        # None / empty
        (None, ""),
        ("", ""),
    ],
)
def test_parse_k8s_quantity_memory(val: object, expected: str) -> None:
    result = parse_k8s_quantity(val, is_cpu=False)
    # Allow small floating-point rounding differences for SI-unit conversions
    try:
        assert abs(float(result) - float(expected)) < 1e-3
    except ValueError:
        assert result == expected
