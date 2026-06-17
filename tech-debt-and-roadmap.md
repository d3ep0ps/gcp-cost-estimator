# GCP Cost Estimator — State of the Project, Technical Debt & Roadmap

*Written: 2026-06-17. Derived from reading plans 1–6, all source modules, and the test suite.*

---

## 1. Where We Stand Right Now

**~93% GCP spend coverage is complete.** Tiers 1–5 (23 services) are fully implemented, tested, and wired through the MCP adapter. The core architecture — deterministic engine, modular pricing registry, TDD discipline — is solid and has scaled cleanly from 1 service to 23.

### Done (services.md tiers 1–5)

| Tier | Services | Share |
|---|---|---|
| 1 — Core infrastructure | Compute Engine, Cloud Storage, GKE, Cloud SQL, BigQuery | ~60% |
| 2 — Serverless & containers | Cloud Run, Cloud Functions, App Engine | ~15% |
| 3 — Databases | Spanner, Firestore, Memorystore, Bigtable, AlloyDB | ~8% |
| 4 — Networking | CDN, DNS, NAT, VPC/static IPs, Cloud Armor, LB (partial), Egress (partial) | ~5% |
| 5 — Data & analytics | Pub/Sub, Dataflow, Dataproc | ~5% |

Cross-cutting infrastructure that is complete: MCP adapter with all tools/resources/prompts, HTTP/SSE adapter with bearer auth, CLI adapter, SQLite pricing cache with atomic-swap refresh, compare/advisory/what-if tools, JSON+CSV+Markdown renderers, structured logging, observability timing, `catalog://defaults` and `catalog://coverage` resources.

### What's Left: Tier 6 (plan6.md, ~4% remaining spend)

Three services remain unimplemented. No source or test files exist for any of them yet. Each needs the standard five-touchpoint treatment: validation → SKU mapping → IaC parsing → catalog → tests.

| Service | Steps | Notes |
|---|---|---|
| Filestore | FS-1 (validation), FS-2 (SKU/pricing), FS-3 (IaC parsing) | 6 tiers; Custom Performance → `unpriced[]`; Backups → `unpriced[]` |
| Vertex AI inference endpoints | VAI-1, VAI-2, VAI-3 | Dedicated endpoints → representative defaults; Shared endpoints → `unpriced[]`; Per-prediction charges always `unpriced[]` |
| Artifact Registry | AR-1, AR-2, AR-3 | Storage + egress billing; all capacity from representative defaults |
| Tier 6 integration test | T6-1 | Combined end-to-end; `catalog://coverage` updated to 97% |

After T6-1, the 90% spend-coverage target stated in ADR-011 is reached (and exceeded at ~97%).

---

## 2. Technical Debt

Organized by priority: things that will hurt soon vs. things that are just untidy.

### 2a. Load Balancing and Network Egress are "partial"

Both are marked `done (partial)` in `services.md`. Load Balancing (`google_compute_forwarding_rule`, `google_compute_global_forwarding_rule`) and VPC egress (derived from instances) have incomplete billing model coverage. This affects any customer with significant traffic shaping, and egress is a top-10 cost driver for data-intensive workloads. These are not deferred — they're acknowledged gaps inside already-"done" services. They need explicit `unpriced[]` entries with accurate reason strings *at minimum*, and full modeling if the billing API exposes the relevant SKUs clearly.

**Recommended action:** define an explicit acceptance criterion per service for what "done" means (e.g., which billing components are modeled and which are `unpriced[]`), and encode the coverage boundary in a test. Right now there is no failing test protecting the partial coverage boundary.

### 2b. Validation stubs in Tier 4 networking modules

Four validation modules — `vpc.py`, `armor.py`, `dns.py`, `nat.py` — each contain only a `pass` body. This means Terraform resources for those services bypass the entire validation/normalization pipeline silently. No errors, no warnings, no defaults applied. For a codebase that's strict about "fail loud, never under-report," this is inconsistent and risks producing $0 estimates for misconfigured resources without surfacing an assumption.

**Recommended action:** implement at minimum `normalize_*` functions that apply the representative defaults from the `CATALOG_DEFAULTS` entries and write tests asserting those defaults are recorded in `assumptions[]`.

### 2c. `terraform_hcl.py` is 868 lines and growing

The HCL parser started as a single file and every new service added more branches. It now handles 20+ resource types. It violates SRP in the same way the monolithic pricing mapper did before modularization. Parsing logic for each service family (compute, serverless, databases, networking, analytics) is interleaved with shared helpers.

**Recommended action:** mirror the pricing modularization pattern from CLAUDE.md — extract per-service parsers into `core/iac/gcp/compute.py`, `core/iac/gcp/serverless.py`, etc., each exporting a `parse_{resource_type}(block) -> Resource` function, dispatched through the existing registry. The interface is already in `core/iac/base.py`.

### 2d. Advisory logic lives in `compare.py`, not `advisory.py`

Milestones 7.1 and 7.2 in `plan.md` called for `core/advisory.py`. `suggest_cheaper_machine_types` and `find_unpriced` ended up in `compare.py` (currently 427 lines), which also owns `compare_regions`, `compare_estimates`, and `what_if`. These are two distinct concerns — comparison (diffing two estimates) and advisory (generating recommendations from one estimate). Mixing them makes the module harder to extend and test in isolation.

**Recommended action:** extract `suggest_cheaper_machine_types` and `find_unpriced` into `core/advisory.py`, update imports in the MCP adapter. Low-risk refactor with existing tests as the safety net.

### 2e. `catalog.py` is 531 lines of data

`core/catalog.py` is a large flat dict of defaults and coverage data. As Tier 6 adds three more services it'll grow further. It's not a logic bug but it makes the file unwieldy to scan and diff.

**Recommended action:** split into `core/catalog/defaults.py` and `core/catalog/coverage.py`, re-exported from `core/catalog/__init__.py`. Zero behavior change; much easier to maintain.

### 2f. Exception `pass` in `serverless.py` swallows errors silently

Lines 312 and 319 in `core/pricing/gcp/serverless.py` contain bare `pass` in exception handlers. These suppress errors during SKU resolution and produce silent `unpriced[]` entries that may not carry the right reason string. Per the project's own "fail loud" principle, suppressed exceptions should at minimum log a structured warning with the exception details.

**Recommended action:** replace bare `pass` with `logger.warning("...", exc_info=True)` and assert in tests that a failed SKU lookup produces a correctly-annotated `unpriced[]` entry, not a silent gap.

### 2g. No CI pipeline visible in the repo

`CLAUDE.md` references CI and a coverage gate but there is no `.github/workflows/`, `.gitlab-ci.yml`, or equivalent in the repo. Coverage enforcement exists only as a local `pytest --cov` invocation. This means every contributor relying on the gate either runs it locally (if they remember) or skips it.

**Recommended action:** add a minimal CI config (GitHub Actions or equivalent) running `uv run ruff check . && uv run mypy src && uv run pytest --cov=gcp_cost_estimator --cov-branch --cov-fail-under=90`. This is a one-file change that closes the process gap.

### 2h. `hcl2` has no type stubs (`# type: ignore[import-untyped]`)

The `python-hcl2` library has no type stubs and the import is suppressed with `type: ignore`. This means the entire HCL parsing layer is untyped at the boundary. Any structural change to the hcl2 output (different list/dict nesting) won't be caught by mypy — only by tests at runtime.

**Recommended action:** add inline stub overloads for the three or four `hcl2` functions actually used, or switch to a thin typed wrapper module that narrows the return types. This is low-effort and restores mypy coverage at the most structurally complex part of the codebase.

### 2i. Integration tests require live network — can't run in isolation

`test_integration_gcp_api.py` and `test_integration_sql_api.py` exist but are not runnable without outbound network access and real GCP credentials. There's no documented `pytest -m integration` marker separating them from the unit suite, no skip guard for missing credentials, and no CI job that runs them in a controlled environment. As written they'll fail or be skipped silently depending on environment.

**Recommended action:** add `@pytest.mark.integration` to all network-touching tests, configure `pytest.ini` to exclude the `integration` mark by default, and document the opt-in invocation in the README. Also add a credential-missing guard (`pytest.importorskip` or a custom skip fixture) so the tests skip gracefully rather than error.

---

## 3. Roadmap — How to Evolve the MCP

These are capabilities that go beyond the current "list-price GCP cost estimate from Terraform" scope. Ordered roughly from "natural next step" to "significant new capability."

### Phase 1 — Complete and harden the current scope

**3.1 Finish Tier 6 (Filestore, Vertex AI, Artifact Registry)** — completes the 97% coverage promise from ADR-011. This is implementation work, not design work; `plan6.md` is the spec.

**3.2 Fix the partial-done services** — Load Balancing and egress billing need explicit scope boundaries (modeled vs. `unpriced[]`) backed by tests. Currently the coverage claim is soft.

**3.3 Harden validation for networking** — Implement the four stub validators (vpc, armor, dns, nat) with at minimum default-application and basic constraint checks.

**3.4 Add CI** — Single workflow file, closes the biggest process gap.

### Phase 2 — SKU freshness and pricing accuracy

**3.5 Scheduled cache refresh as an MCP tool** — The cache refresh logic exists (`gcp_fetch.py`) but is only invoked manually. Expose a `schedule_cache_refresh` MCP tool or a server-startup hook that refreshes if the cache is older than 72h. Currently a cold install with no internet will price everything at $0.

**3.6 Cache staleness warnings in estimates** — ADR for this exists (plan.md Step 8.2) and there's a `test_observability.py`. Verify the stale-cache warning is actually present in the `Estimate` output; add it as a first-class field if not.

**3.7 Multi-region pricing tiers as data, not code** — Cloud Run, Cloud Functions 1st gen, and several Tier 4 services have region-to-tier mappings encoded as Python dicts. As GCP adds regions these need manual updates. Move these to the SQLite cache so they're refreshable without a code deploy.

### Phase 3 — Discount and commitment modeling

The current design is deliberately list-price-only. Phase 3 breaks that constraint for opt-in use cases.

**3.8 Committed Use Discount (CUD) modeling** — Compute Engine, Cloud SQL, Cloud Spanner, and BigQuery all have 1- and 3-year CUD programs. The MCP could accept a `commitments` block in the resource model and produce a "list price vs. committed price" comparison. This is the single highest-impact pricing accuracy improvement for steady-state workloads.

**3.9 Sustained Use Discount (SUD) estimation** — Compute Engine SUDs are automatic (no commitment required) and can halve the effective instance price for 24/7 resources. A `sud_eligible` flag on the resource + a `apply_suds: bool` parameter on `estimate_infrastructure` would let callers opt in.

**3.10 Free-tier awareness** — Cloud Run, Cloud Functions, BigQuery, and Cloud Storage all have significant free tiers. Currently every estimate says "list price only, free tier not applied." A `apply_free_tier: bool` flag with explicit free-tier thresholds (sourced from the cache) would make estimates more realistic for low-volume workloads.

### Phase 4 — Multi-IaC and multi-cloud

**3.11 OpenTofu parser** — OpenTofu is a drop-in Terraform replacement with identical HCL; the existing parser works already. What's missing is explicit testing with OpenTofu plan JSON output (minor schema differences) and documentation that it's supported.

**3.12 Pulumi Python/TypeScript parser** — Pulumi state files (`.pulumi/state/`) expose provisioned resource shapes in JSON. A `PulumiStateParser` implementing `IaCParser` could consume these without touching the core. High value for teams that have moved off Terraform.

**3.13 AWS CDK / CloudFormation parser** — CloudFormation templates expose resource types and properties in JSON/YAML. This is a bigger leap because it requires an AWS `PricingProvider`, but the plugin architecture (`IaCParser`, `PricingProvider`, `SkuMapper`) was designed exactly for this. The model is cloud-neutral by ADR-001.

**3.14 AWS pricing provider** — The AWS Pricing API (Bulk Pricing API + AWS Price List API) has a similar structure to the GCP Billing API. Implementing `AwsPricingProvider` and a Terraform-to-AWS `SkuMapper` would be the first multi-cloud milestone. This unlocks `compare_regions` across clouds — "would this workload cost less on GCP or AWS?"

### Phase 5 — GitOps and workflow integration

**3.15 Pull request cost diff tool** — A `diff_estimate` MCP tool that takes two `ResourceModel` objects (e.g., main branch vs. PR branch) and produces a cost delta report: which resources were added/removed/resized and what the monthly cost change is. Designed to be called from a CI bot that comments on PRs.

**3.16 GitHub Actions integration** — A pre-built composite action that runs `parse_terraform` → `estimate_infrastructure` → `diff_estimate` against a base branch and fails the PR if the monthly cost delta exceeds a configurable threshold. This turns the MCP into a cost gate in CI.

**3.17 Terraform Cloud / Atlantis webhook adapter** — These tools can post plan JSON to a webhook on every `terraform plan`. A thin HTTP adapter (the skeleton already exists in `http/app.py`) could receive that JSON, run it through the estimator, and post a cost summary as a PR comment or Slack message.

### Phase 6 — Reconciliation and actuals

The estimator currently works entirely from IaC — it has no access to what GCP actually charged. Phase 6 closes that loop.

**3.18 Billing export reconciliation tool** — GCP's BigQuery billing export gives actual SKU-level spend by resource. A `reconcile_estimate` MCP tool could accept a billing export CSV/JSON and a resource model, match line items by resource name/SKU, and produce an "estimated vs. actual" table. This is the most direct way to measure and improve estimator accuracy.

**3.19 Historical cost import to the SQLite cache** — The pricing cache currently only stores current list prices. Storing a time series of prices would allow the estimator to show price trends and flag when a SKU's price changed since the last estimate — useful for contracts with multi-year pricing locks.

**3.20 Label-based cost allocation** — GCP resources carry labels (`env: production`, `team: payments`). The Terraform parser already reads labels (they're in the resource model's `attributes`). A `group_by_label` parameter on `estimate_infrastructure` would let callers see cost broken down by team, environment, or any other label axis — useful for chargeback/showback scenarios.

### Phase 7 — Intelligence at the MCP boundary

These capabilities belong in the MCP layer (prompts, resources) rather than core, keeping the deterministic engine clean.

**3.21 Richer advisory prompts** — The existing `optimize-cost` prompt is a starting point. Richer versions could include: "given this estimate, which resources have the highest cost-per-unit-of-value ratio?", "what would happen to this estimate if I moved to Spot/Preemptible VMs?", "show me the top 3 cost optimizations by ROI."

**3.22 `estimate-from-architecture-diagram` prompt** — An MCP prompt that guides the host LLM through extracting a resource model from an architecture diagram (image or Miro/draw.io export) rather than from Terraform. The server validates the result; the LLM does the extraction. This extends estimating to teams without IaC.

**3.23 Cost anomaly explanation tool** — A `explain_cost_spike` tool that takes a billing export period with an anomalous cost and an existing resource model, then identifies which SKU/resource combination most likely explains the spike. Pure SQL analytics over the SQLite cache + billing data — no LLM inside.

**3.24 Streaming large estimates via MCP** — For large Terraform codebases (hundreds of resources), `estimate_infrastructure` can take several seconds. MCP supports streaming responses; the server could emit partial estimates resource-by-resource using `mcp.stream()`, giving the host LLM (and the user) progressive feedback rather than a long wait for a single response.

---

## 4. The One-Sentence Version

Tiers 1–5 are done and solid; finish Tier 6 (three services), fix the four networking validation stubs, extract the HCL parser into per-service modules, add CI, then the natural evolution is CUD/SUD discount modeling → PR cost diffs in CI → multi-cloud (AWS) → billing reconciliation.
