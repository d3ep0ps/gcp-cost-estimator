"""Tests for resolve_machine_type_specs — Phase 0.5.

TDD-as-BDD: every test was written BEFORE the implementation.
All expected values are hand-computed from GCP public documentation:
  https://cloud.google.com/compute/docs/machine-resource
  https://cloud.google.com/compute/docs/general-purpose-machines

Test categories
---------------
1. Rule engine — standard families (the core of ADR-009)
2. Rule engine — N1 family per-family ratio overrides
3. Rule engine — memory-optimised subtypes (megamem / ultramem)
4. Shared-core static overrides (layer 2)
5. Custom machine type patterns (layer 3)
6. Input robustness (case, whitespace)
7. Unknown / unpriceable types
8. Integration: GcpSkuMapper still works with new resolver
"""

import sqlite3

import pytest

from gcp_billing_mcp.core.model import Resource
from gcp_billing_mcp.core.pricing.cache import init_db, update_cache
from gcp_billing_mcp.core.pricing.gcp import GcpSkuMapper, resolve_machine_type_specs

# ---------------------------------------------------------------------------
# 1. Rule engine — standard families
#    Hand-computed: vCPUs = trailing number, RAM = vCPUs x ratio
#    standard → 4.0 GB/vCPU  (all families except N1)
#    highmem  → 8.0 GB/vCPU  (all families except N1)
#    highcpu  → 1.0 GB/vCPU  (all families except N1)
# ---------------------------------------------------------------------------


def test_rule_engine_n2_standard_4() -> None:
    """N2 standard-4: 4 vCPUs x 4.0 GB = 16.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-standard-4")
    assert vcpu == 4
    assert ram == 16.0


def test_rule_engine_n2_standard_8() -> None:
    """N2 standard-8: 8 vCPUs x 4.0 GB = 32.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-standard-8")
    assert vcpu == 8
    assert ram == 32.0


def test_rule_engine_n2_standard_96() -> None:
    """N2 standard-96: largest standard N2 — 96 vCPUs x 4.0 GB = 384.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-standard-96")
    assert vcpu == 96
    assert ram == 384.0


def test_rule_engine_n2d_standard_2() -> None:
    """N2D (AMD EPYC) standard-2 follows identical ratio as N2."""
    vcpu, ram = resolve_machine_type_specs("n2d-standard-2")
    assert vcpu == 2
    assert ram == 8.0


def test_rule_engine_e2_standard_2() -> None:
    """E2 standard-2: 2 vCPUs x 4.0 GB = 8.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-standard-2")
    assert vcpu == 2
    assert ram == 8.0


def test_rule_engine_e2_standard_32() -> None:
    """E2 standard-32: 32 vCPUs x 4.0 GB = 128.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-standard-32")
    assert vcpu == 32
    assert ram == 128.0


def test_rule_engine_c2_standard_4() -> None:
    """C2 (Compute-optimised) standard-4: 4 vCPUs x 4.0 GB = 16.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("c2-standard-4")
    assert vcpu == 4
    assert ram == 16.0


def test_rule_engine_c2d_standard_8() -> None:
    """C2D standard-8: same ratio as C2."""
    vcpu, ram = resolve_machine_type_specs("c2d-standard-8")
    assert vcpu == 8
    assert ram == 32.0


def test_rule_engine_c3_standard_4() -> None:
    """C3 standard-4 (3rd-gen compute-optimised): same standard ratio."""
    vcpu, ram = resolve_machine_type_specs("c3-standard-4")
    assert vcpu == 4
    assert ram == 16.0


def test_rule_engine_c4_standard_8() -> None:
    """C4 standard-8: a newer family — proves zero code change needed for new families."""
    vcpu, ram = resolve_machine_type_specs("c4-standard-8")
    assert vcpu == 8
    assert ram == 32.0


def test_rule_engine_t2d_standard_2() -> None:
    """T2D (Tau VM, AMD) standard-2: 2 vCPUs x 4.0 GB = 8.0 GB."""
    vcpu, ram = resolve_machine_type_specs("t2d-standard-2")
    assert vcpu == 2
    assert ram == 8.0


def test_rule_engine_t2a_standard_1() -> None:
    """T2A (Tau VM, ARM) standard-1: 1 vCPU x 4.0 GB = 4.0 GB."""
    vcpu, ram = resolve_machine_type_specs("t2a-standard-1")
    assert vcpu == 1
    assert ram == 4.0


def test_rule_engine_z3_standard_88() -> None:
    """Z3 (storage-optimised) standard-88: 88 vCPUs x 4.0 GB = 352.0 GB."""
    vcpu, ram = resolve_machine_type_specs("z3-standard-88")
    assert vcpu == 88
    assert ram == 352.0


def test_rule_engine_hypothetical_future_family() -> None:
    """Future GCP family (e.g. 'z5-standard-16') resolves correctly with zero code change.

    This is the key regression test for ADR-009: if Google announces z5 tomorrow,
    the rule engine prices it automatically after the next SKU cache refresh.
    """
    vcpu, ram = resolve_machine_type_specs("z5-standard-16")
    assert vcpu == 16
    assert ram == 64.0


# ---------------------------------------------------------------------------
# 2. Rule engine — highmem and highcpu subtypes
#    highmem → 8.0 GB/vCPU
#    highcpu → 1.0 GB/vCPU
# ---------------------------------------------------------------------------


def test_rule_engine_n2_highmem_4() -> None:
    """N2 highmem-4: 4 vCPUs x 8.0 GB = 32.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-highmem-4")
    assert vcpu == 4
    assert ram == 32.0


def test_rule_engine_n2_highmem_8() -> None:
    """N2 highmem-8: 8 vCPUs x 8.0 GB = 64.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-highmem-8")
    assert vcpu == 8
    assert ram == 64.0


def test_rule_engine_n2_highmem_128() -> None:
    """N2 highmem-128: 128 vCPUs x 8.0 GB = 1024.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-highmem-128")
    assert vcpu == 128
    assert ram == 1024.0


def test_rule_engine_n2_highcpu_4() -> None:
    """N2 highcpu-4: 4 vCPUs x 1.0 GB = 4.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-highcpu-4")
    assert vcpu == 4
    assert ram == 4.0


def test_rule_engine_n2_highcpu_32() -> None:
    """N2 highcpu-32: 32 vCPUs x 1.0 GB = 32.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-highcpu-32")
    assert vcpu == 32
    assert ram == 32.0


def test_rule_engine_e2_highcpu_8() -> None:
    """E2 highcpu-8: 8 vCPUs x 1.0 GB = 8.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-highcpu-8")
    assert vcpu == 8
    assert ram == 8.0


# ---------------------------------------------------------------------------
# 3. Rule engine — N1 per-family ratio overrides
#    n1 standard → 3.75 GB/vCPU (NOT 4.0 like other families)
#    n1 highmem  → 6.5 GB/vCPU
#    n1 highcpu  → 0.9 GB/vCPU
# ---------------------------------------------------------------------------


def test_rule_engine_n1_standard_1_override() -> None:
    """N1 standard-1: 1 vCPU x 3.75 GB = 3.75 GB (N1-specific ratio, not 4.0)."""
    vcpu, ram = resolve_machine_type_specs("n1-standard-1")
    assert vcpu == 1
    assert pytest.approx(ram, rel=1e-3) == 3.75


def test_rule_engine_n1_standard_4_override() -> None:
    """N1 standard-4: 4 vCPUs x 3.75 GB = 15.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n1-standard-4")
    assert vcpu == 4
    assert pytest.approx(ram, rel=1e-3) == 15.0


def test_rule_engine_n1_standard_8_override() -> None:
    """N1 standard-8: 8 vCPUs x 3.75 GB = 30.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n1-standard-8")
    assert vcpu == 8
    assert pytest.approx(ram, rel=1e-3) == 30.0


def test_rule_engine_n1_standard_96_override() -> None:
    """N1 standard-96: 96 vCPUs x 3.75 GB = 360.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n1-standard-96")
    assert vcpu == 96
    assert pytest.approx(ram, rel=1e-3) == 360.0


def test_rule_engine_n1_highmem_4_override() -> None:
    """N1 highmem-4: 4 vCPUs x 6.5 GB = 26.0 GB RAM (N1-specific, not 8.0)."""
    vcpu, ram = resolve_machine_type_specs("n1-highmem-4")
    assert vcpu == 4
    assert pytest.approx(ram, rel=1e-3) == 26.0


def test_rule_engine_n1_highmem_8_override() -> None:
    """N1 highmem-8: 8 vCPUs x 6.5 GB = 52.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n1-highmem-8")
    assert vcpu == 8
    assert pytest.approx(ram, rel=1e-3) == 52.0


def test_rule_engine_n1_highcpu_4_override() -> None:
    """N1 highcpu-4: 4 vCPUs x 0.9 GB = 3.6 GB RAM (N1-specific, not 1.0)."""
    vcpu, ram = resolve_machine_type_specs("n1-highcpu-4")
    assert vcpu == 4
    assert pytest.approx(ram, rel=1e-3) == 3.6


def test_rule_engine_n1_highcpu_32_override() -> None:
    """N1 highcpu-32: 32 vCPUs x 0.9 GB = 28.8 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n1-highcpu-32")
    assert vcpu == 32
    assert pytest.approx(ram, rel=1e-3) == 28.8


# ---------------------------------------------------------------------------
# 4. Rule engine — Memory-optimised subtypes
#    megamem  → 14.933 GB/vCPU  (M1/M2)
#    ultramem → 24.025 GB/vCPU  (M1)
# ---------------------------------------------------------------------------


def test_rule_engine_m1_megamem_96() -> None:
    """M1 megamem-96: 96 vCPUs x 14.933 GB ≈ 1433.57 GB RAM.

    Reference: https://cloud.google.com/compute/docs/memory-optimized-machines
    GCP lists 1,433.6 GiB for m1-megamem-96.
    """
    vcpu, ram = resolve_machine_type_specs("m1-megamem-96")
    assert vcpu == 96
    assert pytest.approx(ram, rel=1e-3) == 96 * 14.933


def test_rule_engine_m1_ultramem_40() -> None:
    """M1 ultramem-40: 40 vCPUs x 24.025 GB = 961.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("m1-ultramem-40")
    assert vcpu == 40
    assert pytest.approx(ram, rel=1e-3) == 40 * 24.025


def test_rule_engine_m1_ultramem_80() -> None:
    """M1 ultramem-80: 80 vCPUs x 24.025 GB = 1922.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("m1-ultramem-80")
    assert vcpu == 80
    assert pytest.approx(ram, rel=1e-3) == 80 * 24.025


def test_rule_engine_m3_ultramem_32() -> None:
    """M3 ultramem-32 (3rd-gen memory-optimised): same ratio as M1 ultramem."""
    vcpu, ram = resolve_machine_type_specs("m3-ultramem-32")
    assert vcpu == 32
    assert pytest.approx(ram, rel=1e-3) == 32 * 24.025


# ---------------------------------------------------------------------------
# 5. Shared-core static overrides (Layer 2)
#    These are irregular types that do not follow the N-based naming convention.
#    Source: https://cloud.google.com/compute/docs/general-purpose-machines#e2-shared-core
# ---------------------------------------------------------------------------


def test_shared_core_e2_micro() -> None:
    """e2-micro: 2 billing vCPUs (shared), 1.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-micro")
    assert vcpu == 2
    assert ram == 1.0


def test_shared_core_e2_small() -> None:
    """e2-small: 2 billing vCPUs (shared), 2.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-small")
    assert vcpu == 2
    assert ram == 2.0


def test_shared_core_e2_medium() -> None:
    """e2-medium: 2 billing vCPUs (shared), 4.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-medium")
    assert vcpu == 2
    assert ram == 4.0


def test_shared_core_f1_micro() -> None:
    """f1-micro (N1 shared-core): 1 billing vCPU, 0.6 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("f1-micro")
    assert vcpu == 1
    assert pytest.approx(ram, rel=1e-3) == 0.6


def test_shared_core_g1_small() -> None:
    """g1-small (N1 shared-core): 1 billing vCPU, 1.7 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("g1-small")
    assert vcpu == 1
    assert pytest.approx(ram, rel=1e-3) == 1.7


# ---------------------------------------------------------------------------
# 6. Custom machine type patterns (Layer 3)
#    Handles bare custom-N-MMMM and family-prefixed n2-custom-N-MMMM forms.
#    RAM is specified in megabytes and converted to gigabytes by dividing by 1024.
# ---------------------------------------------------------------------------


def test_custom_type_6vcpu_20480mb() -> None:
    """custom-6-20480: 6 vCPUs, 20480 MB / 1024 = 20.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("custom-6-20480")
    assert vcpu == 6
    assert ram == 20.0


def test_custom_type_8vcpu_32768mb() -> None:
    """custom-8-32768: 8 vCPUs, 32768 MB / 1024 = 32.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("custom-8-32768")
    assert vcpu == 8
    assert ram == 32.0


def test_custom_type_2vcpu_2048mb() -> None:
    """custom-2-2048: 2 vCPUs, 2048 MB / 1024 = 2.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("custom-2-2048")
    assert vcpu == 2
    assert ram == 2.0


def test_n1_prefixed_custom_type() -> None:
    """n1-custom-4-8192: N1 custom — 4 vCPUs, 8192 MB / 1024 = 8.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n1-custom-4-8192")
    assert vcpu == 4
    assert ram == 8.0


def test_n2_prefixed_custom_type() -> None:
    """n2-custom-4-16384: N2 custom — 4 vCPUs, 16384 MB / 1024 = 16.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2-custom-4-16384")
    assert vcpu == 4
    assert ram == 16.0


def test_e2_prefixed_custom_type() -> None:
    """e2-custom-2-4096: E2 custom — 2 vCPUs, 4096 MB / 1024 = 4.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("e2-custom-2-4096")
    assert vcpu == 2
    assert ram == 4.0


def test_n2d_prefixed_custom_type() -> None:
    """n2d-custom-4-8192: N2D custom — 4 vCPUs, 8192 MB / 1024 = 8.0 GB RAM."""
    vcpu, ram = resolve_machine_type_specs("n2d-custom-4-8192")
    assert vcpu == 4
    assert ram == 8.0


# ---------------------------------------------------------------------------
# 7. Input robustness
# ---------------------------------------------------------------------------


def test_input_uppercase_normalised() -> None:
    """Input should be normalised to lowercase; UPPER-CASE must not break resolution."""
    vcpu, ram = resolve_machine_type_specs("N2-STANDARD-4")
    assert vcpu == 4
    assert ram == 16.0


def test_input_mixed_case_normalised() -> None:
    """Mixed case input is normalised correctly."""
    vcpu, ram = resolve_machine_type_specs("n2-Standard-4")
    assert vcpu == 4
    assert ram == 16.0


def test_input_leading_trailing_whitespace_stripped() -> None:
    """Leading/trailing whitespace is stripped before resolution."""
    vcpu, ram = resolve_machine_type_specs("  n2-standard-4  ")
    assert vcpu == 4
    assert ram == 16.0


def test_empty_string_returns_zero() -> None:
    """Empty string returns (0, 0.0) — must not raise."""
    vcpu, ram = resolve_machine_type_specs("")
    assert vcpu == 0
    assert ram == 0.0


# ---------------------------------------------------------------------------
# 8. Unknown / unpriceable types → (0, 0.0)
# ---------------------------------------------------------------------------


def test_completely_unknown_type_returns_zero() -> None:
    """A completely unknown type name returns (0, 0.0) and must not raise."""
    vcpu, ram = resolve_machine_type_specs("warp-speed-9")
    assert vcpu == 0
    assert ram == 0.0


def test_partial_match_unknown_subtype_returns_zero() -> None:
    """A known family + unknown subtype (no ratio) returns (0, 0.0).

    e.g. 'n2-turbo-4' — 'turbo' is not a valid GCP subtype.
    """
    vcpu, ram = resolve_machine_type_specs("n2-turbo-4")
    assert vcpu == 0
    assert ram == 0.0


def test_known_family_missing_vcpu_count_returns_zero() -> None:
    """A name with no trailing vCPU number fails gracefully."""
    vcpu, ram = resolve_machine_type_specs("n2-standard")
    assert vcpu == 0
    assert ram == 0.0


def test_old_style_string_without_dash_returns_zero() -> None:
    """A name that has no dashes at all returns (0, 0.0)."""
    vcpu, ram = resolve_machine_type_specs("n2standard4")
    assert vcpu == 0
    assert ram == 0.0


# ---------------------------------------------------------------------------
# 9. Regression: MACHINE_SPECS values must NOT change
#    These are the exact values from the old dictionary; the new resolver must
#    return identical results to prevent any regression in existing estimates.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "machine_type, expected_vcpu, expected_ram",
    [
        # Old MACHINE_SPECS entries — all must produce the same result
        ("n1-standard-1", 1, 3.75),
        ("n1-standard-2", 2, 7.50),
        ("n1-standard-4", 4, 15.00),
        ("n1-standard-8", 8, 30.00),
        ("n2-standard-2", 2, 8.00),
        ("n2-standard-4", 4, 16.00),
        ("n2-standard-8", 8, 32.00),
        ("e2-standard-2", 2, 8.00),
        ("e2-standard-4", 4, 16.00),
        ("e2-standard-8", 8, 32.00),
        ("e2-medium", 2, 4.00),  # shared-core override
    ],
)
def test_old_machine_specs_values_preserved(
    machine_type: str, expected_vcpu: int, expected_ram: float
) -> None:
    """Regression: all values from the deleted MACHINE_SPECS dict must survive unchanged."""
    vcpu, ram = resolve_machine_type_specs(machine_type)
    assert vcpu == expected_vcpu, f"{machine_type}: expected vcpu={expected_vcpu}, got {vcpu}"
    assert pytest.approx(ram, rel=1e-3) == expected_ram, (
        f"{machine_type}: expected ram={expected_ram}, got {ram}"
    )


# ---------------------------------------------------------------------------
# 10. Integration: GcpSkuMapper works end-to-end with new resolver
#     These tests prove that removing MACHINE_SPECS does not break the mapper.
# ---------------------------------------------------------------------------


@pytest.fixture
def mapper_db(tmp_path: pytest.TempPathFactory) -> str:
    """Minimal DB fixture for mapper integration tests."""
    db_path = str(tmp_path / "mapper_test.db")
    conn = sqlite3.connect(db_path)
    init_db(conn)
    conn.close()

    skus = [
        {
            "sku_id": "SKU-N2-CPU",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N2 Instance Core running in Americas",
        },
        {
            "sku_id": "SKU-N2-RAM",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N2 Instance Ram running in Americas",
        },
        {
            "sku_id": "SKU-N1-CPU",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0475,
            "sku_group": "CPU",
            "description": "N1 Predefined Instance Core running in Americas",
        },
        {
            "sku_id": "SKU-N1-RAM",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0063,
            "sku_group": "RAM",
            "description": "N1 Predefined Instance Ram running in Americas",
        },
        {
            "sku_id": "SKU-E2-CPU",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "h",
            "unit_price": 0.0210,
            "sku_group": "CPU",
            "description": "E2 Instance Core running in Americas",
        },
        {
            "sku_id": "SKU-E2-RAM",
            "service": "compute engine",
            "region": "us-central1",
            "unit": "GiBy.mo",
            "unit_price": 0.0028,
            "sku_group": "RAM",
            "description": "E2 Instance Ram running in Americas",
        },
    ]
    update_cache(db_path, "gcp", skus, "2026-06-03T12:00:00Z")
    return db_path


def test_mapper_n2_standard_4_correct_qty(mapper_db: str) -> None:
    """GcpSkuMapper: n2-standard-4 → 4.0 vCPU qty and 16.0 GB RAM qty.

    Hand-computed cost per month:
      CPU: 4 x 0.0475 x 730h = $138.70
      RAM: 16 x 0.0063 = $0.1008/GiBy.mo
    """
    resource = Resource(
        provider="gcp",
        resource_id="vm-n2s4",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
    )
    mapper = GcpSkuMapper(mapper_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert unpriced == [], f"Expected no unpriced items, got: {unpriced}"
    assert len(mappings) == 2

    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    ram_map = next(m for m in mappings if m["component"] == "ram")

    assert vcpu_map["qty"] == 4.0
    assert vcpu_map["sku_id"] == "SKU-N2-CPU"
    assert ram_map["qty"] == 16.0
    assert ram_map["sku_id"] == "SKU-N2-RAM"


def test_mapper_n1_standard_4_n1_ratio(mapper_db: str) -> None:
    """GcpSkuMapper: n1-standard-4 → 4 vCPUs, 15.0 GB RAM (N1 ratio, not 16.0).

    This is the key regression guard: n1-standard-4 has 15 GB, not 16 GB.
    An error here means the N1 override was not applied.
    """
    resource = Resource(
        provider="gcp",
        resource_id="vm-n1s4",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n1-standard-4"},
    )
    mapper = GcpSkuMapper(mapper_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert unpriced == [], f"Expected no unpriced items, got: {unpriced}"
    ram_map = next(m for m in mappings if m["component"] == "ram")
    assert pytest.approx(ram_map["qty"], rel=1e-3) == 15.0, (
        "n1-standard-4 must have 15.0 GB (3.75 GB/vCPU x 4), not 16.0 GB (4.0 x 4)"
    )


def test_mapper_e2_medium_shared_core(mapper_db: str) -> None:
    """GcpSkuMapper: e2-medium (shared-core) → 2 vCPUs billing qty, 4.0 GB RAM.

    Tests that the shared-core override is respected end-to-end.
    """
    resource = Resource(
        provider="gcp",
        resource_id="vm-e2m",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "e2-medium"},
    )
    mapper = GcpSkuMapper(mapper_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert unpriced == [], f"Expected no unpriced items, got: {unpriced}"
    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    ram_map = next(m for m in mappings if m["component"] == "ram")

    assert vcpu_map["qty"] == 2.0
    assert ram_map["qty"] == 4.0


def test_mapper_unknown_machine_type_reported_unpriced(mapper_db: str) -> None:
    """GcpSkuMapper: an unknown machine type is reported in unpriced[], never silently dropped.

    This is the 'fail loud' guarantee: the unpriced list must have an entry,
    and the reason must mention the machine type name.
    """
    resource = Resource(
        provider="gcp",
        resource_id="vm-unknown",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "quantum-turbo-9000"},
    )
    mapper = GcpSkuMapper(mapper_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert mappings == []
    assert len(unpriced) == 1
    assert (
        "quantum-turbo-9000" in unpriced[0]["reason"].lower()
        or "unknown" in unpriced[0]["reason"].lower()
    ), f"Unpriced reason must mention the type or say 'unknown'. Got: {unpriced[0]['reason']}"


def test_mapper_custom_machine_type_priced_correctly(mapper_db: str) -> None:
    """GcpSkuMapper: custom-4-16384 (4 vCPUs, 16 GB) is priced via the rule engine.

    Verifies that custom types don't need to be in any dict to be priced.
    """
    resource = Resource(
        provider="gcp",
        resource_id="vm-custom",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-custom-4-16384"},
    )
    mapper = GcpSkuMapper(mapper_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert unpriced == [], f"Expected no unpriced items, got: {unpriced}"
    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    ram_map = next(m for m in mappings if m["component"] == "ram")

    assert vcpu_map["qty"] == 4.0
    assert ram_map["qty"] == 16.0  # 16384 MB / 1024


def test_mapper_quantity_multiplied_correctly(mapper_db: str) -> None:
    """GcpSkuMapper: resource.quantity multiplies both vCPU and RAM qty.

    E.g. 3 x n2-standard-4 → qty = 3 x 4 = 12 vCPUs, 3 x 16 = 48 GB RAM.
    """
    resource = Resource(
        provider="gcp",
        resource_id="vm-fleet",
        service="compute",
        kind="gce_instance",
        region="us-central1",
        attributes={"machine_type": "n2-standard-4"},
        quantity=3,
    )
    mapper = GcpSkuMapper(mapper_db)
    mappings, unpriced = mapper.map_resource_to_skus(resource)

    assert unpriced == []
    vcpu_map = next(m for m in mappings if m["component"] == "vcpu")
    ram_map = next(m for m in mappings if m["component"] == "ram")

    assert vcpu_map["qty"] == 12.0  # 4 x 3
    assert ram_map["qty"] == 48.0  # 16 x 3
