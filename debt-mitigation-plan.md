# Tech Debt Mitigation Plan

*Written: 2026-06-18. Based on full codebase audit after Tier 6 completion.*
*Tier 6 status: Filestore, Vertex AI, Artifact Registry are implemented.*

---

## Debt inventory (current state)

| ID | Debt item | Risk | Complexity |
|---|---|---|---|
| D1 | Tier 6 mapper uses raw Terraform kind names instead of canonical service/kind | High — correctness | Low |
| D2 | `validate_*` bodies are `pass` for vpc, armor, dns, nat, compute | High — silent under-reporting | Low |
| D3 | Integration tests not excluded from default `pytest` run | High — false CI failures | Low |
| D4 | Bare `pass` in `serverless.py` exception handlers | Medium — silent data loss | Low |
| D5 | `terraform_hcl.py` 908 lines / `terraform_plan.py` 687 lines — both with duplicated 30+ resource dispatch | Medium — maintainability | High |
| D6 | Advisory logic (`suggest_cheaper_machine_types`, `find_unpriced`) in `compare.py` | Medium — SRP violation | Low |
| D7 | `catalog.py` 602 lines — defaults + coverage in one flat file | Low — maintainability | Low |
| D8 | `hcl2` import suppressed with `# type: ignore[import-untyped]` | Low — mypy blind spot | Medium |
| D9 | No CI pipeline | Medium — process gap | Low |
| D10 | Load Balancing and network egress marked "partial" with no test boundary | Medium — accuracy | Medium |

---

## Wave structure

Waves are independent — each can be started and completed without waiting for another.
Within a wave, steps are ordered: do them top-to-bottom.

```
Wave 1 — Correctness & Safety    (fix what's wrong now, lowest risk to change)
Wave 2 — Architecture            (most complex, refactor with test safety net)
Wave 3 — Process & DX            (CI, typing, catalog split)
Wave 4 — Accuracy                (fill the partial coverage gaps)
```

Recommended execution order: Wave 1 first (it fixes bugs), then Waves 2/3 in parallel (independent), then Wave 4.

---

## Wave 1 — Correctness & Safety

*Prerequisites: none. Can start immediately.*
*Goal: eliminate all silent data loss and false test failures. No new features.*

---

### W1-1 — Fix Tier 6 canonical kind naming in mapper.py

**What's wrong:** `filestore`, `vertex_ai`, and `artifact_registry` were wired into `mapper.py` using raw Terraform resource type strings (`resource.kind == "google_filestore_instance"`) instead of the `resource.service == "X" and resource.kind == "Y"` pattern used by every other service. This means the mapper branch is bypassed for any resource model where the IaC parser assigns a different kind string, and the inconsistency makes the dispatch logic harder to read.

**Files to change:**
- `src/gcp_cost_estimator/core/pricing/gcp/mapper.py` — lines 442–450
- `src/gcp_cost_estimator/core/iac/terraform_hcl.py` — kind assignment for Tier 6 resource types
- `src/gcp_cost_estimator/core/iac/terraform_plan.py` — same
- `src/gcp_cost_estimator/core/validation/gcp/__init__.py` — ensure VALIDATORS/NORMALIZERS keys match

**Canonical naming to establish (matching the Tier 1–5 pattern):**

| Terraform type | `service` | `kind` |
|---|---|---|
| `google_filestore_instance` | `"filestore"` | `"filestore_instance"` |
| `google_vertex_ai_endpoint` | `"vertex_ai"` | `"vertex_ai_endpoint"` |
| `google_artifact_registry_repository` | `"artifact_registry"` | `"artifact_registry_repository"` |

**Steps:**
1. Write failing tests that construct a `Resource` with the correct `service`/`kind` values and assert the mapper routes them correctly.
2. Update the three kind assignments in `terraform_hcl.py` (kind-mapping pass) and `terraform_plan.py`.
3. Update `mapper.py` dispatch branches to use `resource.service == "filestore" and resource.kind == "filestore_instance"` pattern.
4. Ensure `VALIDATORS`/`NORMALIZERS` in `core/validation/gcp/__init__.py` use matching keys.
5. Run full suite; update any fixture that referenced the old raw kind strings.

**Done when:** No `resource.kind == "google_*"` pattern remains in `mapper.py`. All Tier 6 tests pass.

---

### W1-2 — Implement `validate_*` for Tier 4 networking services

**What's wrong:** `validate_vpc`, `validate_armor`, `validate_dns`, `validate_nat`, and `normalize_compute` are all empty `pass` bodies. The `normalize_*` functions apply defaults correctly, but validation is entirely bypassed — no constraint checking, no `unpriced[]` population for unsupported configurations, no warnings for ambiguous inputs.

**Files to change:**
- `src/gcp_cost_estimator/core/validation/gcp/vpc.py`
- `src/gcp_cost_estimator/core/validation/gcp/armor.py`
- `src/gcp_cost_estimator/core/validation/gcp/dns.py`
- `src/gcp_cost_estimator/core/validation/gcp/nat.py`
- `src/gcp_cost_estimator/core/validation/gcp/compute.py` (`normalize_compute` is also a `pass`)

**What to implement per service:**

*VPC (`compute_address`):*
- Validate `address_type` is one of `EXTERNAL`, `INTERNAL` — emit error if unrecognised.
- If `address_type == "INTERNAL"`, surface as `unpriced[]` with reason `"Internal static IPs are free; no billing line item."` rather than silently producing a $0 line.
- Warn if both `on_spot_vm` and `on_forwarding_rule` are `True` simultaneously (mutually exclusive pricing rules).

*Cloud Armor (`compute_security_policy`):*
- Validate `rule_count` ≥ 0; emit error if negative.
- If `policy_type` attribute is `"CLOUD_ARMOR_EDGE"`, surface as `unpriced[]` with reason `"Edge Security policies have different pricing not yet modelled."`.
- Warn if `monthly_requests` > 1 billion (likely a unit error — user may have entered per-second rate).

*Cloud DNS (`dns_managed_zone`):*
- Validate `visibility` is `"public"` or `"private"` — emit error otherwise.
- If `visibility == "private"`, surface as `unpriced[]` with reason `"Private DNS zones are free; no billing line item."`.
- Validate `monthly_queries` > 0 — warn if zero (estimate will be $0).

*Cloud NAT (`nat_gateway`):*
- Validate `num_vms` ≥ 1 and `num_nat_ips` ≥ 1.
- Validate `monthly_data_processed_gb` ≥ 0.
- Warn if `num_nat_ips` exceeds `num_vms` by 3× or more (likely a configuration mistake).

*Compute (`normalize_compute`):*
- Apply `runtime_hours_per_month = 730` default if absent.
- Apply `disk_type = "pd-standard"` default if absent.
- Record both in `assumptions[]`.

**Steps:**
1. Write failing tests for each service's validation behaviour (invalid input → error, unsupported config → `unpriced[]`, edge case → warning).
2. Implement the `validate_*` functions, following the existing pattern in `sql.py`, `storage.py`, or `container.py` as reference.
3. Implement `normalize_compute` (apply defaults, record in `assumptions[]`).
4. Run full suite.

**Done when:** All four `validate_*` bodies produce structured errors/warnings/unpriced entries. Test coverage ≥ 90% on new code.

---

### W1-3 — Fix integration test filtering

**What's wrong:** `pyproject.toml` defines the `integration` pytest marker but `addopts` does not exclude it. Every `uv run pytest` invocation attempts the integration tests, which require live network and GCP credentials, causing failures or noisy skips in every local/CI environment.

**Files to change:**
- `pyproject.toml`
- `tests/test_integration_gcp_api.py`
- `tests/test_integration_sql_api.py`
- `tests/test_integration_sql_e2e.py`

**Steps:**
1. Add `-m "not integration"` to `addopts` in `pyproject.toml` so the default run excludes integration tests.
2. Add a credential guard to each integration test file:
   ```python
   import os, pytest
   pytestmark = pytest.mark.integration
   
   @pytest.fixture(autouse=True, scope="session")
   def require_gcp_credentials():
       if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and \
          not os.environ.get("GCP_BILLING_PROJECT"):
           pytest.skip("GCP credentials not configured — skipping integration tests")
   ```
3. Document the opt-in invocation in `README.md`:
   ```
   # Run unit tests only (default):
   uv run pytest
   
   # Run integration tests (requires GCP credentials):
   GCP_BILLING_PROJECT=my-project uv run pytest -m integration
   ```

**Done when:** `uv run pytest` runs cleanly with no integration test failures or skips. README documents the opt-in.

---

### W1-4 — Fix bare `pass` in `serverless.py` SKU selection

**What's wrong:** Lines 312 and 319 in `core/pricing/gcp/serverless.py` are bare `pass` statements inside a SKU selection loop that silently discard idle CPU and idle RAM SKU rows. The intent is to skip those rows during active-SKU selection, but the `pass` is structurally indistinguishable from a swallowed exception or an unfinished implementation. Additionally, there is no test asserting that a missing idle SKU produces a properly-annotated `unpriced[]` entry.

**Files to change:**
- `src/gcp_cost_estimator/core/pricing/gcp/serverless.py`

**Steps:**
1. Write a failing test: when idle SKUs are absent from the cache, `map_cloud_run_service` with `min_instance_count > 0` must return an `unpriced[]` entry with reason `"No idle CPU/RAM SKU found for region {region}"`, not silently produce $0.
2. Replace the two bare `pass` statements with explicit `continue` (to make the intent clear) and add a post-loop guard that appends to `unpriced[]` if no idle SKU was found but one was required (i.e., `min_instance_count > 0`).
3. Add a `logger.debug(...)` call identifying the skipped row for diagnostics.

**Done when:** The failing test passes. No bare `pass` remains in exception-path code.

---

## Wave 2 — Architecture Refactoring

*Prerequisites: Wave 1 complete (clean baseline before restructuring).*
*Goal: eliminate the two monolithic IaC parsers and the mixed-concern compare module.*
*This is the highest-complexity wave. Each step has its own safe-to-merge checkpoint.*

---

### W2-1 — Extract per-service IaC parser modules

**What's wrong:** `terraform_hcl.py` (908 lines) and `terraform_plan.py` (687 lines) both contain two-pass dispatch logic (kind-mapping + attribute extraction) for 30+ Terraform resource types. They are structurally identical to the monolithic `gcp.py` pricing mapper that was already modularized. Adding a new resource type requires editing *both* files in parallel. The files will grow linearly with every new service.

**Target structure:**
```
src/gcp_cost_estimator/core/iac/
  base.py              # IaCParser interface (unchanged)
  terraform_hcl.py     # Thin orchestrator: HCL file loading + dispatch only
  terraform_plan.py    # Thin orchestrator: plan JSON loading + dispatch only
  gcp/
    __init__.py        # Registry: RESOURCE_TYPE_MAP dict (Terraform type → parser fn)
    compute.py         # parse_compute_instance(), parse_compute_disk()
    sql.py             # parse_sql_database_instance()
    storage.py         # parse_storage_bucket()
    container.py       # parse_container_cluster(), parse_container_node_pool()
    bigquery.py        # parse_bigquery_dataset(), parse_bigquery_table()
    serverless.py      # parse_cloud_run_v2_service(), parse_cloud_run_v2_job(),
                       # parse_cloudfunctions_function(), parse_cloudfunctions2_function(),
                       # parse_app_engine_standard_app_version(),
                       # parse_app_engine_flexible_app_version()
    databases.py       # parse_spanner_instance(), parse_firestore_database(),
                       # parse_redis_instance(), parse_memorystore_instance(),
                       # parse_bigtable_instance(), parse_alloydb_cluster(),
                       # parse_alloydb_instance()
    networking.py      # parse_compute_backend_bucket(), parse_compute_backend_service(),
                       # parse_dns_managed_zone(), parse_compute_router_nat(),
                       # parse_compute_address(), parse_compute_security_policy()
    analytics.py       # parse_pubsub_topic(), parse_pubsub_subscription(),
                       # parse_pubsub_lite_topic(), parse_pubsub_lite_subscription(),
                       # parse_dataflow_job(), parse_dataproc_cluster(),
                       # parse_dataproc_serverless_batch()
    storage_ai.py      # parse_filestore_instance(), parse_vertex_ai_endpoint(),
                       # parse_artifact_registry_repository()
```

**Interface each parser function must satisfy:**
```python
# core/iac/gcp/compute.py
def parse_compute_instance(
    res_id: str,
    attrs: dict[str, Any],
    labels: dict[str, str],
) -> Resource:
    ...

def parse_compute_disk(
    res_id: str,
    attrs: dict[str, Any],
    labels: dict[str, str],
) -> Resource:
    ...
```

The `__init__.py` registry maps Terraform resource type strings to their parser functions:
```python
# core/iac/gcp/__init__.py
from .compute import parse_compute_instance, parse_compute_disk
...

RESOURCE_TYPE_MAP: dict[str, Callable[[str, dict[str, Any], dict[str, str]], Resource]] = {
    "google_compute_instance": parse_compute_instance,
    "google_compute_disk": parse_compute_disk,
    "google_storage_bucket": parse_storage_bucket,
    ...
}
```

The thin `terraform_hcl.py` orchestrator becomes:
```python
from gcp_cost_estimator.core.iac.gcp import RESOURCE_TYPE_MAP

class TerraformHclParser(IaCParser):
    def parse(self, path: str) -> ResourceModel:
        ...  # file loading + HCL flattening (keep existing logic)
        for res_type, res_id, attrs, labels in resources:
            parser_fn = RESOURCE_TYPE_MAP.get(res_type)
            if parser_fn is None:
                unrecognised.append(res_type)
                continue
            resources_out.append(parser_fn(res_id, attrs, labels))
        ...
```

`terraform_plan.py` uses the same `RESOURCE_TYPE_MAP` — a single registry, two consumers.

**Migration steps (each is a safe commit):**

1. **Create `core/iac/gcp/__init__.py`** with empty `RESOURCE_TYPE_MAP = {}`. All tests still pass (nothing routes through it yet).

2. **Extract `compute.py`** — move `parse_compute_instance` and `parse_compute_disk` logic out of both HCL and plan parsers into `core/iac/gcp/compute.py`. Register in `RESOURCE_TYPE_MAP`. Update both parsers to use the map for these two types. Run tests.

3. **Extract `sql.py`** — same pattern. Run tests.

4. **Extract `storage.py`** — Run tests.

5. **Extract `container.py`** — Run tests.

6. **Extract `bigquery.py`** — Run tests.

7. **Extract `serverless.py`** — largest service group; includes Cloud Run, Cloud Functions, App Engine. Run tests.

8. **Extract `databases.py`** — Spanner, Firestore, Memorystore, Bigtable, AlloyDB. Run tests.

9. **Extract `networking.py`** — CDN, DNS, NAT, VPC, Armor. Run tests.

10. **Extract `analytics.py`** — Pub/Sub, Dataflow, Dataproc. Run tests.

11. **Extract `storage_ai.py`** — Filestore, Vertex AI, Artifact Registry. Run tests.

12. **Delete dead branches** — once all types are routed through `RESOURCE_TYPE_MAP`, remove the old if-elif chains from `terraform_hcl.py` and `terraform_plan.py`. Run full suite. Both files should now be under 100 lines each.

**Invariants throughout:**
- No test file changes during the migration (the tests define the contract; the refactoring must satisfy them as written).
- Each step is a passing commit. Never leave the suite red between steps.
- The `RESOURCE_TYPE_MAP` is the only place a Terraform type string is mentioned — no duplication between HCL and plan parsers.

**Done when:** `terraform_hcl.py` < 100 lines, `terraform_plan.py` < 100 lines, all resource type logic lives in `core/iac/gcp/`, full suite green.

---

### W2-2 — Extract `core/advisory.py` from `compare.py`

**What's wrong:** `compare.py` mixes two unrelated concerns: *comparison* (diffing two estimates or repricing across regions) and *advisory* (generating recommendations from a single resource). `suggest_cheaper_machine_types` (267 lines) and `find_unpriced` belong in a separate `core/advisory.py` module per the original plan.md design intent.

**Files to change:**
- `src/gcp_cost_estimator/core/compare.py` — remove the two advisory functions
- `src/gcp_cost_estimator/core/advisory.py` — new file
- `src/gcp_cost_estimator/mcp/server.py` — update import
- `tests/test_compare.py` — split advisory tests to `tests/test_advisory.py`

**Steps:**
1. Create `core/advisory.py`. Move `suggest_cheaper_machine_types` and `find_unpriced` verbatim; add module docstring.
2. Update `mcp/server.py` import from `core.compare` to `core.advisory` for those two functions.
3. In `compare.py`, replace the moved functions with `from gcp_cost_estimator.core.advisory import suggest_cheaper_machine_types, find_unpriced` temporarily (keeps existing import paths working with no test changes).
4. Create `tests/test_advisory.py` by moving the advisory test cases from `test_compare.py`. Remove them from `test_compare.py`.
5. Remove the re-export shim from `compare.py`.
6. Run full suite.

**Done when:** `compare.py` contains only `compare_regions`, `compare_estimates`, `what_if`. `advisory.py` contains only `suggest_cheaper_machine_types`, `find_unpriced`. No cross-imports between them. Tests pass.

---

## Wave 3 — Process & Developer Experience

*Prerequisites: none (fully independent from Waves 1 and 2).*
*Goal: add CI, restore mypy coverage at the HCL boundary, split the catalog.*

---

### W3-1 — Add GitHub Actions CI

**What's wrong:** There is no CI pipeline. The coverage gate, lint, and type-check exist only as local `uv run ...` invocations. Every contributor must remember to run them.

**File to create:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          python-version: "3.14"
      - name: Install dependencies
        run: uv sync --all-extras
      - name: Lint
        run: uv run ruff check .
      - name: Format check
        run: uv run ruff format --check .
      - name: Type check
        run: uv run mypy src
      - name: Unit tests + coverage
        run: uv run pytest --cov=gcp_cost_estimator --cov-branch --cov-fail-under=90
        # Integration tests excluded by default via pyproject.toml addopts: -m "not integration"
```

**Steps:**
1. Create `.github/workflows/ci.yml` with the content above.
2. Verify locally that all three commands pass before opening the PR.
3. Add branch protection rule requiring `CI / test` to pass before merge (document in README).

**Done when:** Every push and PR triggers CI. Green badge in README.

---

### W3-2 — Add typed wrapper for `hcl2`

**What's wrong:** `from hcl2 import ...` is suppressed with `# type: ignore[import-untyped]`. The `hcl2.load()` return type is `dict[str, Any]` but mypy cannot verify that, so any structural changes in hcl2's output format are invisible to the type checker.

**File to create:** `src/gcp_cost_estimator/core/iac/_hcl2_wrapper.py`

```python
# _hcl2_wrapper.py
"""Typed shim around the untyped python-hcl2 library.

hcl2.load() returns dict[str, list[dict[str, Any]]] where keys are Terraform
block types ("resource", "variable", "locals", etc.) and values are lists of
block bodies.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import hcl2  # type: ignore[import-untyped]

HclDocument = dict[str, list[dict[str, Any]]]


def load_hcl(path: Path) -> HclDocument:
    """Load a single .tf file and return its parsed HCL document."""
    with path.open() as fh:
        result: HclDocument = hcl2.load(fh)
    return result
```

**Steps:**
1. Create `_hcl2_wrapper.py` with the typed shim above.
2. In `terraform_hcl.py`, replace `import hcl2` and all `hcl2.load(...)` calls with `from gcp_cost_estimator.core.iac._hcl2_wrapper import load_hcl, HclDocument`.
3. Remove the `# type: ignore[import-untyped]` comment.
4. Run `uv run mypy src` — all hcl2-related `type: ignore` suppressions should disappear.
5. Run full suite.

**Done when:** `mypy src` produces zero suppressions related to hcl2. `terraform_hcl.py` imports the wrapper, not hcl2 directly.

---

### W3-3 — Split `catalog.py` into submodules

**What's wrong:** `core/catalog.py` is 602 lines containing two unrelated data structures: `CATALOG_DEFAULTS` (450 lines, one entry per service per default field) and `CATALOG_COVERAGE` (147 lines, the service coverage table). These will grow with every new service. The file is hard to diff and review.

**Target structure:**
```
src/gcp_cost_estimator/core/catalog/
  __init__.py       # re-exports CATALOG_DEFAULTS, CATALOG_COVERAGE (backward compat)
  defaults.py       # CATALOG_DEFAULTS dict
  coverage.py       # CATALOG_COVERAGE dict
```

**Steps:**
1. Create `core/catalog/` directory with `__init__.py`, `defaults.py`, `coverage.py`.
2. Move `CATALOG_DEFAULTS` to `defaults.py`; move `CATALOG_COVERAGE` to `coverage.py`.
3. In `__init__.py`: `from .defaults import CATALOG_DEFAULTS; from .coverage import CATALOG_COVERAGE`.
4. No changes to any import site — the existing `from gcp_cost_estimator.core.catalog import CATALOG_DEFAULTS, CATALOG_COVERAGE` continues to work.
5. Delete the old `core/catalog.py`.
6. Run full suite.

**Done when:** `catalog.py` is gone; `core/catalog/` directory contains three files each under 200 lines; all imports resolve; tests pass.

---

## Wave 4 — Accuracy

*Prerequisites: Wave 1 (especially W1-2 for consistent validation patterns to follow).*
*Goal: close the "partial" coverage gaps in Load Balancing and network egress.*

---

### W4-1 — Complete Load Balancing billing model

**What's wrong:** `google_compute_forwarding_rule` and `google_compute_global_forwarding_rule` are marked `done (partial)` in `services.md`. The IaC parser produces a resource but the billing coverage boundary is undefined — there are no tests asserting which components are modelled and which go to `unpriced[]`.

**Billing components to model:**

| Component | Unit | Notes |
|---|---|---|
| Forwarding rule charge | rule/hour | $0.025/hr per rule beyond the first 5 (first 5 are free — list price only, so model all as $0.025/hr per the list-price-only principle) |
| Ingress data processing | GiB | Application Load Balancers only — Network LBs have no data processing charge |
| Premium network tier | — | rules in Standard tier have different pricing; model as `unpriced[]` if `network_tier == "STANDARD"` |

Source to verify: https://cloud.google.com/load-balancing/pricing (verify before committing fixtures).

**Steps:**
1. Fetch and read the Load Balancing pricing page; identify the current SKU IDs via the Billing Pricing API.
2. Write failing tests encoding the expected billing components and `unpriced[]` entries for unsupported configurations.
3. Implement `map_forwarding_rule()` in `core/pricing/gcp/compute.py` (or a new `core/pricing/gcp/load_balancer.py`).
4. Implement `validate_forwarding_rule()` in `core/validation/gcp/compute.py`.
5. Update IaC parsers (via the new `core/iac/gcp/compute.py` after W2-1, or directly if W2-1 is not yet done).
6. Update `services.md` status from `done (partial)` to `done`.

**Done when:** `services.md` shows Load Balancing as `done`. Tests document the modelled billing components and the `unpriced[]` boundary.

---

### W4-2 — Harden network egress billing

**What's wrong:** Network egress is marked `done (partial)` — it is derived from instances but the coverage boundary (which traffic types, which regions, which Compute Engine resource types) is not documented in a test.

**Components to audit and explicitly scope:**

| Egress type | Current status | Target |
|---|---|---|
| Internet egress from Compute Engine VMs | modelled | verify SKU IDs are current |
| Inter-region egress (same continent) | ? | model or `unpriced[]` with reason |
| Inter-region egress (different continent) | ? | model or `unpriced[]` with reason |
| Egress to Google services (same region) | free | ensure no line item generated |
| Egress to Cloud Storage (same region) | free | ensure no line item generated |
| Cloud SQL egress | ? | model or `unpriced[]` with reason |
| GKE node-to-node egress | ? | model or `unpriced[]` with reason |

Source: https://cloud.google.com/vpc/network-pricing (verify before committing fixtures).

**Steps:**
1. Fetch pricing page; create an explicit coverage boundary table (what's modelled vs `unpriced[]` vs free).
2. Write tests asserting each boundary case produces the correct output.
3. Implement missing `unpriced[]` entries for currently-silent gaps.
4. Update `services.md` status from `done (partial)` to `done`.

**Done when:** `services.md` shows Network egress as `done`. Every traffic type is either modelled, explicitly `unpriced[]` with a documented reason, or confirmed free with a test asserting $0.

---

## Execution checklist

For each work item, the definition of done is:

- [ ] Failing test written first that encodes the expected behaviour.
- [ ] Implementation makes the test pass.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run mypy src` passes.
- [ ] `uv run pytest` passes (after W1-3 is done: unit tests only by default).
- [ ] Coverage ≥ 90% on new/changed `core/` code.
- [ ] `services.md` and `CLAUDE.md` updated if a scope decision changed.

---

## Dependency graph

```
W1-1 ─────────────────────────────────────────────────────┐
W1-2 ─────────────────────────────────────────────────────┤
W1-3 (enables reliable CI gate for all subsequent work)   │  Wave 1
W1-4 ─────────────────────────────────────────────────────┘
         │
         ▼
W2-1 ──────── (most complex; do steps 1-12 one commit at a time)  ┐
W2-2 ──────── (simple extract; 1 day)                              │  Wave 2
         │                                                          │
         ▼                                                          │
W3-1 ──────── (independent; no blockers)                          ─┤  Wave 3
W3-2 ──────── (independent after W2-1 if HCL wrapper is cleaner)  │
W3-3 ──────── (independent; no blockers)                          ─┘
         │
         ▼
W4-1 ──────── (needs W1-2 pattern for validation style)           ┐  Wave 4
W4-2 ──────── (needs W1-2 pattern for validation style)           ┘
```

Waves 3 and 4 can run in parallel with Wave 2 (except W3-2 which is easier after W2-1).

---

## Estimated effort

| Item | Effort | Who can parallelize |
|---|---|---|
| W1-1 Kind naming fix | 0.5 day | Anyone |
| W1-2 Validation stubs | 1 day | Anyone (4 services, can be split) |
| W1-3 Integration test filter | 0.5 day | Anyone |
| W1-4 Serverless bare pass | 0.5 day | Anyone |
| W2-1 IaC parser split | 3–4 days | Best done by one person; 12 commits |
| W2-2 Advisory extract | 0.5 day | Anyone |
| W3-1 CI | 0.5 day | Anyone |
| W3-2 hcl2 typed wrapper | 0.5 day | Anyone; easier after W2-1 |
| W3-3 Catalog split | 0.5 day | Anyone |
| W4-1 Load Balancing | 1–2 days | Anyone with GCP pricing API access |
| W4-2 Egress hardening | 1 day | Anyone with GCP pricing API access |
| **Total** | **~10 days** | |
