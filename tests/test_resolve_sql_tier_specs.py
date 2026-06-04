# SPDX-License-Identifier: Apache-2.0

from gcp_cost_estimator.core.pricing.gcp import resolve_sql_tier_specs


def test_resolve_db_custom_2_7680_returns_2_vcpu_7_5_gb() -> None:
    """Verify db-custom-2-7680 resolves to 2 vCPU and 7.5 GB RAM."""
    vcpu, ram = resolve_sql_tier_specs("db-custom-2-7680")
    assert vcpu == 2
    assert ram == 7.5


def test_resolve_db_custom_4_15360_returns_4_vcpu_15_gb() -> None:
    """Verify db-custom-4-15360 resolves to 4 vCPU and 15 GB RAM."""
    vcpu, ram = resolve_sql_tier_specs("db-custom-4-15360")
    assert vcpu == 4
    assert ram == 15.0


def test_resolve_db_n1_standard_2_returns_2_vcpu_7_5_gb() -> None:
    """Verify db-n1-standard-2 (standard tier) resolves to 2 vCPU and 7.5 GB RAM."""
    vcpu, ram = resolve_sql_tier_specs("db-n1-standard-2")
    assert vcpu == 2
    assert ram == 7.5


def test_resolve_db_n1_highmem_4_returns_4_vcpu_26_gb() -> None:
    """Verify db-n1-highmem-4 resolves to 4 vCPU and 26.0 GB RAM."""
    vcpu, ram = resolve_sql_tier_specs("db-n1-highmem-4")
    assert vcpu == 4
    assert ram == 26.0


def test_resolve_unknown_tier_returns_zero_zero() -> None:
    """Verify that an unknown tier returns (0, 0.0) gracefully."""
    vcpu, ram = resolve_sql_tier_specs("db-unknown-tier")
    assert vcpu == 0
    assert ram == 0.0
