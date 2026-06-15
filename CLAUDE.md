# CLAUDE.md — GCP Cost Estimator MCP Server

Guidance for any AI agent (or human) working in this repository. Read this first.

## GCP Cost Estimator references (authoritative pricing sources)
All pricing data and SKU semantics derive from these. When in doubt about pricing behavior, consult them — do not guess:
- Cloud Billing Pricing API (REST): https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest
- GCP SKU groups: https://cloud.google.com/skus/sku-groups
- GCP product pricing list: https://cloud.google.com/pricing/list

**Documentation verification rule (mandatory):** Before committing any fixture price, SKU ID, billing unit, or service constraint, fetch the relevant official pricing page and verify the value. Never use training-data memory for prices or SKU semantics. Cite the source URL and verification date in a comment next to the fixture. See `services.md` for per-service documentation links.

## What this project is
A **GCP Cost Estimator MCP server**: a deterministic server that exposes GCP cost-estimation capabilities (IaC parsing, SKU pricing, cost calculation, comparison, reporting) as **MCP tools, resources, and prompts**. The connecting MCP host (Claude Code, Gemini CLI, Antigravity, Cursor) supplies all natural-language intelligence. **There is no LLM inside this server.**

Authoritative design: `gcp-cost-estimator-server-architecture.md`. If code and that doc disagree, stop and reconcile before proceeding.

**Active extension plans:**
- `plan.md` — original v1 milestone plan (Milestones 0–8, all substantially complete).
- `plan1.md` — Cloud SQL full coverage extension (Steps CS-1 through CS-10).
- `plan2.md` — Tier 1 remaining services: Cloud Storage, GKE, BigQuery (Steps GCS-*, GKE-*, BQ-*, T2-1).
- `plan3.md` — Tier 2 Serverless & Containers: Cloud Run, Cloud Functions, App Engine (Steps SVL-1 through SVL-11). **Current active work.**
- `plan4.md` — Tier 3 Databases: Spanner, Firestore, Memorystore, Bigtable, AlloyDB.
- `services.md` — target services list for 90% GCP spend coverage; implementation order and per-service documentation links.

## Non-negotiable principles
1. **Deterministic core.** No randomness, no network, no LLM on the hot path. Same input + same cache snapshot ⇒ identical output. If a function can't be made deterministic, it doesn't belong in `core/`.
2. **Library-first.** All logic lives in `src/gcp_cost_estimator/core/`. The MCP, HTTP, and CLI layers are *thin adapters* that call core — they contain no business logic.
3. **List price only.** Never invent prices. Every priced line item must carry a real `sku_id` and the cache `snapshot_ts`. No SUD/CUD/negotiated discounts in v1. Always attach the disclaimer.
4. **Fail loud, never under-report.** Unmappable/unpriced resources are returned in an explicit `unpriced[]` list — never silently dropped or zero-filled.
5. **Extensible by registry.** Cloud providers, IaC formats, and output formats are plugins behind interfaces (`IaCParser`, `PricingProvider`/`SkuMapper`, `CostCalculator`, `OutputRenderer`). v1 implements GCP / Terraform / JSON+CSV+markdown only. No GCP/Terraform/format assumptions may leak into shared code.
6. **Cloud-neutral model.** The canonical resource model must stay expressive enough to represent AWS/Azure later. No GCP-only fields at the top level; provider specifics go in `attributes`.

## Development methodology — TDD as BDD (strict)
We practice **Test-Driven Development driven by behavior** to avoid scope drift and hallucinated functionality.

- **Behavior first.** Every unit of work starts from an acceptance criterion traceable to an FR in the architecture doc. If there's no FR, there's no code — raise it as an open question instead of inventing behavior.
- **Red → Green → Refactor, every time.**
  1. Write a failing test that encodes the behavior (name it after the behavior, e.g. `test_estimate_includes_disclaimer_and_snapshot_ts`).
  2. Write the minimum code to pass.
  3. Refactor with tests green.
- **No production code without a failing test that demanded it.** If you're tempted to add a capability "while you're here," write the test first or don't add it.
- **Known-answer fixtures for all pricing/math.** Cost calculations are verified against hand-computed expected values committed as fixtures, not against the code's own output.
- **Tests are the spec.** A reviewer should understand each feature by reading its tests. Prefer descriptive test names and Given/When/Then structure.
- **Coverage.** Target ≥ 90% line + branch on `core/`. Adapters (MCP/HTTP/CLI) are smoke/contract-tested. Coverage is a floor, not the goal — behavior coverage matters more than line coverage.
- **Determinism in tests.** No live network. The GCP Pricing API is always mocked/fixtured. A test that hits the network is a bug.

### Definition of Done (per task)
- [ ] Behavior traces to an FR/acceptance criterion.
- [ ] Failing test written first, now passing.
- [ ] Edge/error cases covered (unpriced, unresolved Terraform vars, empty input, stale cache).
- [ ] No business logic in adapters.
- [ ] Lint + type-check + full test suite green.
- [ ] Public functions have docstrings; no dead code.

## Tooling & commands
- **Python:** 3.13+. **Package manager:** `uv` (never pip directly).
- Install: `uv sync`
- Run tests: `uv run pytest`
- Coverage: `uv run pytest --cov=gcp_cost_estimator --cov-branch`
- Lint/format: `uv run ruff check .` and `uv run ruff format .`
- Type-check: `uv run mypy src`
- Run MCP server (stdio): `uv run python -m gcp_cost_estimator.mcp.server`
- Run a single test: `uv run pytest tests/path::test_name -x`

> Always run lint, type-check, and the full suite before declaring a task complete.

## Repo layout
```
src/gcp_cost_estimator/
  core/        # transport-agnostic logic (model, registries, iac, pricing, calc, render)
  mcp/         # MCP adapter: tools/resources/prompts (thin)
  http/        # optional bearer-auth HTTP/SSE adapter (thin)
  cli.py       # optional CLI adapter (thin)
tests/         # mirrors src/; known-answer fixtures under tests/fixtures/
```

## Conventions
- **Clean Code & SOLID:** Strictly follow the guidelines in [clean-code.md](clean-code.md) and [solid.md](solid.md).
- Pydantic (or dataclasses) for the resource model + estimate model; validation centralized in `core/model.py`.
- Pure functions in `core/`; side effects (cache I/O, refresh) isolated and injectable for testing.
- Registries are the only place concrete impls are wired; never import a concrete impl from shared code.
- Errors: typed exceptions in core; adapters translate to MCP/HTTP error shapes.
- Secrets/credentials never logged; redact secret-flagged Terraform attributes before returning a model.
- Conventional commits; small, behavior-scoped commits that pair a test with its implementation.

### Codebase Structure & GCP Pricing Modularization
The GCP pricing mapper is modularized under `src/gcp_cost_estimator/core/pricing/gcp/` to satisfy SRP and OCP. Do not add code to a monolithic file. To add pricing support for a new GCP resource:
1. Create a new module file under `src/gcp_cost_estimator/core/pricing/gcp/<service>.py` (e.g. `gcs.py`, `sql.py`).
2. Implement the mapping function: `map_<resource_kind>(resource: Resource, cursor: sqlite3.Cursor) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]`.
3. Import and delegate to this function inside `GcpSkuMapper` in `mapper.py`.
4. Ensure any shared specifications/resolvers (e.g., machine/tier specs) are placed in `specs.py` and re-exported in `__init__.py`.

### Codebase Structure & GCP Validation/Normalization Modularization
The GCP validation and normalization logic is modularized under `src/gcp_cost_estimator/core/validation/gcp/` to satisfy SRP and OCP. Do not add service-specific validation or normalization code to `validate.py`. To add validation or normalization support for a new GCP resource/service:
1. Create a new module file under `src/gcp_cost_estimator/core/validation/gcp/<service>.py` (e.g., `storage.py`, `sql.py`).
2. Implement validation and normalization functions:
   - `validate_<service>(r: Resource, errors: list[str], warnings: list[str], unpriced: list[dict[str, Any]]) -> None`
   - `normalize_<service>(r: Resource) -> None`
3. Import and register these functions in `VALIDATORS` and `NORMALIZERS` inside `src/gcp_cost_estimator/core/validation/gcp/__init__.py`.


## Architecture decisions (ADRs)
Key decisions recorded here for quick reference. Full rationale in `gcp-cost-estimator-server-architecture.md` §7.

- **ADR-009 — Rule-based machine type resolver.** `resolve_machine_type_specs()` derives `(vcpu, ram_gb)` from GCP naming conventions (`{family}-{subtype}-{N}`) rather than a static lookup table. Three-layer chain: rule engine → shared-core overrides → custom machine type pattern. This means new GCP machine families are supported automatically with zero code change. Cloud SQL has an analogous `resolve_sql_tier_specs()` that strips the `db-` prefix and delegates to the same rule engine for standard tiers, plus a `db-custom-{N}-{M}` fast path.

- **ADR-010 — Cloud SQL Enterprise Plus supports all DB engines.** As of August 2024 (GA), Enterprise Plus supports MySQL, PostgreSQL, and SQL Server. The earlier constraint "Enterprise Plus excludes SQL Server" in the architecture doc is **superseded**. The correct constraint is: Enterprise Plus SQL Server requires an *Enterprise* SQL Server licence version (`SQLSERVER_*_ENTERPRISE`); Standard/Web/Express licence versions are Enterprise edition only. Any code or test asserting the old exclusion is a bug.

- **ADR-011 — 90% spend coverage target via `services.md`.**
- **ADR-014 — Representative defaults over zero-defaults; working estimate over perfect estimate.** When usage fields are absent (size, query volume, egress, etc.), apply a documented representative default rather than zero. Zero-defaults produce misleadingly cheap estimates. Every default is recorded in `assumptions[]` with its value. Billing dimensions not yet fully modelled are surfaced as `unpriced[]` with a reason — never silently dropped. A "known simplifications" backlog in each plan file tracks what needs improving. See `catalog://defaults` for the full defaults catalog.
- **ADR-013 — `export_estimate` writes files server-side.** Server writes to the caller-supplied path (works for all flows including CI/HTTP with no host LLM). Path sanitisation + `EXPORT_ALLOWED_DIR` validation required in the adapter before any write. `core/` contains no filesystem logic. Tool returns the resolved absolute path on success.
- **ADR-012 — NL extraction via schema + prompt + validation only; no server-side heuristic.** Host LLM uses `schema://resource-model` + `estimate-from-description` prompt; server validates and returns structured errors for self-correction. No `extract_resources` heuristic inside the server — that violates ADR-001. Improvements to NL quality go into the prompt/schema, not `core/`. The service implementation roadmap is tracked in `services.md`. Tier 1 (Compute Engine, Cloud Storage, GKE, Cloud SQL, BigQuery) covers ~60% of typical spend and is the first priority. After Tier 1, the recommended order is Cloud Run → Cloud Functions → Cloud Spanner → Firestore → Memorystore.

## Guardrails for AI agents specifically
- **Do not invent SKUs, prices, machine-type specs, or regions.** If it's not in the cache/fixtures, surface it as unpriced/unknown.
- **Do not invent service billing rules.** Fetch the official pricing page (linked in `services.md`) before implementing any new service. Cite the URL in fixture comments.
- **Do not skip the failing-test step** to "save time." The test is the contract that prevents hallucinated behavior.
- **Do not widen scope** beyond the current task's FR. Park ideas in `plan.md` or `plan1.md` open questions.
- When unsure about GCP pricing semantics, **write a fixture-backed test capturing the assumption** and flag it, rather than guessing in code.
- Keep the architecture doc, `plan.md`/`plan1.md`, and `services.md` updated when a decision changes.
