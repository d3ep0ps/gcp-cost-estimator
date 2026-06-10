# SPDX-License-Identifier: Apache-2.0

import re

# RAM-per-vCPU ratios (GB) — exact values from GCP public documentation.
# These ratios are universal across all families EXCEPT N1 (see _FAMILY_SUBTYPE_OVERRIDES).
_SUBTYPE_RAM_RATIO: dict[str, float] = {
    "standard": 4.0,  # n2-standard-4  → 4 x 4.0 = 16 GB
    "highmem": 8.0,  # n2-highmem-4   → 4 x 8.0 = 32 GB
    "highcpu": 1.0,  # n2-highcpu-4   → 4 x 1.0 = 4 GB
    "megamem": 14.933,  # m1-megamem-96  → 96 x 14.933 ≈ 1433.6 GB
    "ultramem": 24.025,  # m1-ultramem-80 → 80 x 24.025 ≈ 1922.0 GB
}

# Per-family ratio overrides — only N1 breaks the universal ratio for each subtype.
# N1 was GCP's first generation and was designed before the universal ratios were standardised.
_FAMILY_SUBTYPE_OVERRIDES: dict[tuple[str, str], float] = {
    ("n1", "standard"): 3.75,  # n1-standard-4 → 4 x 3.75 = 15.0 GB (NOT 16.0)
    ("n1", "highmem"): 6.5,  # n1-highmem-4  → 4 x 6.5  = 26.0 GB
    ("n1", "highcpu"): 0.9,  # n1-highcpu-4  → 4 x 0.9  = 3.6 GB
}

# Shared-core types: these do NOT follow the {family}-{subtype}-{N} pattern.
# The set is very small and extremely stable — GCP has not added a new shared-core type in years.
_SHARED_CORE_SPECS: dict[str, tuple[int, float]] = {
    "e2-micro": (2, 1.0),  # 2 billing vCPUs (shared), 1 GB RAM
    "e2-small": (2, 2.0),  # 2 billing vCPUs (shared), 2 GB RAM
    "e2-medium": (2, 4.0),  # 2 billing vCPUs (shared), 4 GB RAM
    "f1-micro": (1, 0.6),  # N1 shared-core, 0.6 GB RAM
    "g1-small": (1, 1.7),  # N1 shared-core, 1.7 GB RAM
}

# Regex for standard machine type names: {family}-{subtype}-{N}
# family: 2+ alphanumeric chars starting with a letter (e.g. n2, n2d, t2d, c3d, z3)
# subtype: one or more lowercase letters (standard, highmem, highcpu, megamem, ultramem)
# N: integer vCPU count
# NOTE: the 'custom' keyword must not match as a subtype — it is handled by _CUSTOM_PATTERN.
_STANDARD_PATTERN = re.compile(r"^([a-z][a-z0-9]+)-([a-z]+)-(\d+)$")

# Regex for custom machine types: [family-]custom-N-MMMM
# Matches both bare "custom-4-8192" and prefixed "n2-custom-4-8192", "n1-custom-4-8192", etc.
# A family prefix is any 2+ char alphanumeric token followed by a dash, immediately before 'custom'.
_CUSTOM_PATTERN = re.compile(r"^(?:[a-z][a-z0-9]+-)?custom-(\d+)-(\d+)$")


def _derive_specs_from_name(mt: str) -> tuple[int, float] | None:
    """Layer 1: derive (vcpu, ram_gb) from GCP naming convention.

    Returns None if the machine type name does not match the standard pattern,
    or if the subtype is not in the ratio table (unknown subtype).
    """
    m = _STANDARD_PATTERN.match(mt)
    if not m:
        return None
    family, subtype, vcpu_str = m.group(1), m.group(2), m.group(3)
    vcpu = int(vcpu_str)
    # Family-specific override takes precedence over the universal subtype ratio.
    ratio = _FAMILY_SUBTYPE_OVERRIDES.get((family, subtype)) or _SUBTYPE_RAM_RATIO.get(subtype)
    if ratio is None:
        return None  # Unknown subtype — fall through to next layer
    return vcpu, vcpu * ratio


def resolve_machine_type_specs(machine_type: str) -> tuple[int, float]:
    """Resolve a GCP machine type name to (vcpu, ram_gb).

    Resolution order (ADR-009):
      1. Rule-based derivation from {family}-{subtype}-{N} naming convention.
         Handles all standard GCP families automatically, including future ones.
      2. Static overrides for shared-core types (e2-micro, e2-small, e2-medium,
         f1-micro, g1-small).
      3. Custom machine type pattern: custom-N-MMMM or {family}-custom-N-MMMM.

    Returns (0, 0.0) if unresolvable — the caller must add the resource to unpriced[].
    """
    mt = machine_type.strip().lower()

    # Layer 1: rule engine (covers ~95% of real-world usage)
    result = _derive_specs_from_name(mt)
    if result is not None:
        return result

    # Layer 2: shared-core static overrides
    if mt in _SHARED_CORE_SPECS:
        return _SHARED_CORE_SPECS[mt]

    # Layer 3: custom machine type pattern
    m = _CUSTOM_PATTERN.match(mt)
    if m:
        vcpu = int(m.group(1))
        ram_mb = int(m.group(2))
        return vcpu, ram_mb / 1024.0

    return 0, 0.0


def resolve_sql_tier_specs(tier: str) -> tuple[int, float]:
    """Resolve a Cloud SQL tier spec name to (vcpu, ram_gb).

    Resolution logic:
      1. If custom: parse db-custom-{N}-{M} -> (N, M/1024.0)
      2. If standard: strip the leading 'db-' and delegate to resolve_machine_type_specs.
      3. Return (0, 0.0) if unresolvable.
    """
    t = tier.strip().lower()
    if not t:
        return 0, 0.0

    # Custom machine tier pattern db-custom-{N}-{M}
    if t.startswith("db-custom-"):
        parts = t.split("-")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            vcpu = int(parts[2])
            ram_mb = int(parts[3])
            return vcpu, ram_mb / 1024.0

    # Standard machine tier: strip 'db-' and delegate to resolve_machine_type_specs
    if t.startswith("db-"):
        stripped = t[3:]
        return resolve_machine_type_specs(stripped)

    return 0, 0.0


def resolve_alloydb_instance_specs(cpu_count: int) -> tuple[int, float]:
    """Resolve AlloyDB CPU count to (vcpu, ram_gb) spec."""
    mapping: dict[int, float] = {
        2: 16.0,
        4: 32.0,
        8: 64.0,
        16: 128.0,
        32: 256.0,
        64: 512.0,
        96: 768.0,
        128: 864.0,
    }
    if cpu_count in mapping:
        return cpu_count, mapping[cpu_count]
    return 0, 0.0
