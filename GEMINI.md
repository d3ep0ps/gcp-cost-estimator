# GEMINI.md — GCP Cost Estimator MCP Server

This file provides guidance and instructions for Gemini CLI, Antigravity, or any human developer working in this repository.

## GCP Cost Estimator References (Authoritative Pricing Sources)
All pricing data and SKU semantics derive from these. When in doubt about pricing behavior, consult them — do not guess:
- Cloud Billing Pricing API (REST): https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest
- GCP SKU groups: https://cloud.google.com/skus/sku-groups
- GCP product pricing list: https://cloud.google.com/pricing/list

**Documentation verification rule (mandatory):** Before committing any fixture price, SKU ID, billing unit, or service constraint, fetch the relevant official pricing page and verify the value. Never use training-data memory for prices or SKU semantics. Cite the source URL and verification date in a comment next to the fixture. See `services.md` for per-service documentation links.

## Project Overview
This project is a **GCP Cost Estimator MCP server**: a deterministic server that exposes GCP cost-estimation capabilities (IaC parsing, SKU pricing, cost calculation, comparison, reporting) as **MCP tools, resources, and prompts**.
- The connecting MCP host (Claude Code, Gemini CLI, Antigravity, Cursor) supplies all natural-language intelligence.
- **There is no LLM inside this server.**
- Authoritative design: [gcp-cost-estimator-server-architecture.md](gcp-cost-estimator-server-architecture.md). If code and that doc disagree, stop and reconcile before proceeding.

**Active extension plans:**
- [`plan.md`](plan.md) — original v1 milestone plan (Milestones 0–8, all substantially complete).
- [`plan1.md`](plan1.md) — Cloud SQL full coverage extension (Steps CS-1 through CS-10). **Current active work.**
- [`services.md`](services.md) — target services list for 90% GCP spend coverage; implementation order and per-service documentation links.

## Non-Negotiable Principles
1. **Deterministic Core:** No randomness, no network, no LLM on the hot path. Same input + same cache snapshot ⇒ identical output. If a function cannot be made deterministic, it does not belong in `core/`.
2. **Library-First:** All logic lives in `src/gcp_cost_estimator/core/`. The MCP, HTTP, and CLI layers are *thin adapters* that call core — they contain no business logic.
3. **List Price Only:** Never invent prices. Every priced line item must carry a real `sku_id` and the cache `snapshot_ts`. No SUD/CUD/negotiated discounts in v1. Always attach the disclaimer.
4. **Fail Loud, Never Under-Report:** Unmappable/unpriced resources are returned in an explicit `unpriced[]` list — never silently dropped or zero-filled.
5. **Extensible by Registry:** Cloud providers, IaC formats, and output formats are plugins behind interfaces (`IaCParser`, `PricingProvider`/`SkuMapper`, `CostCalculator`, `OutputRenderer`). v1 implements GCP / Terraform / JSON+CSV+markdown only. No GCP/Terraform/format assumptions may leak into shared code.
6. **Cloud-Neutral Model:** The canonical resource model must stay expressive enough to represent AWS/Azure later. No GCP-only fields at the top level; provider specifics go in `attributes`.

## Development Methodology — TDD as BDD (Strict)
We practice **Test-Driven Development driven by behavior** (TDD-as-BDD) to avoid scope drift and hallucinated functionality.

- **Behavior first:** Every unit of work starts from an acceptance criterion traceable to an FR in the architecture doc. If there is no FR, there is no code — raise it as an open question instead of inventing behavior.
- **Red → Green → Refactor, every time:**
  1. Write a failing test that encodes the behavior (name it after the behavior, e.g. `test_estimate_includes_disclaimer_and_snapshot_ts`).
  2. Write the minimum code to pass.
  3. Refactor with tests green.
- **No production code without a failing test that demanded it:** If you are tempted to add a capability "while you're here," write the test first or do not add it.
- **Known-answer fixtures for all pricing/math:** Cost calculations are verified against hand-computed expected values committed as fixtures, not against the code's own output.
- **Tests are the spec:** A reviewer should understand each feature by reading its tests. Prefer descriptive test names and Given/When/Then structure.
- **Coverage:** Target ≥ 90% line + branch on `core/`. Adapters (MCP/HTTP/CLI) are smoke/contract-tested. Coverage is a floor, not the goal — behavior coverage matters more than line coverage.
- **Determinism in tests:** No live network. The GCP Pricing API is always mocked/fixtured. A test that hits the network is a bug.

### Definition of Done (per task)
- [ ] Behavior traces to an FR/acceptance criterion.
- [ ] Failing test written first, now passing.
- [ ] Edge/error cases covered (unpriced, unresolved Terraform vars, empty input, stale cache).
- [ ] No business logic in adapters.
- [ ] Lint + type-check + full test suite green.
- [ ] Public functions have docstrings; no dead code.

## Commands Reference

Always use `uv` for package management and script execution.

| Task | Command |
| :--- | :--- |
| Install dependencies | `uv sync` |
| Run all tests | `uv run pytest` |
| Run tests with coverage | `uv run pytest --cov=gcp_cost_estimator --cov-branch` |
| Run a specific test | `uv run pytest tests/path/to/test.py::test_name -x` |
| Lint & format checks | `uv run ruff check .` |
| Auto-format code | `uv run ruff format .` |
| Type checking | `uv run mypy src` |
| Run MCP server (stdio) | `uv run python -m gcp_cost_estimator.mcp.server` |

> Always run lint, type-check, and the full test suite before declaring a task complete.

## Repository Layout
- [src/gcp_cost_estimator/](src/gcp_cost_estimator/)
  - [core/](src/gcp_cost_estimator/core/) — Transport-agnostic logic (model, registries, iac, pricing, calc, render)
  - [mcp/](src/gcp_cost_estimator/mcp/) — MCP adapter: tools/resources/prompts (thin)
  - [http/](src/gcp_cost_estimator/http/) — Optional bearer-auth HTTP/SSE adapter (thin)
  - [cli.py](src/gcp_cost_estimator/cli.py) — Optional CLI adapter (thin)
- [tests/](tests/) — Mirrors `src/`; known-answer fixtures under `tests/fixtures/`

## Coding Conventions
- **Clean Code & SOLID:** Strictly follow the repository's clean code practices in [clean-code.md](clean-code.md) and SOLID principles in [solid.md](solid.md).
- **Data Models:** Use Pydantic (or dataclasses) for the resource model + estimate model; validation is centralized in `core/model.py`.
- **Side Effects:** Write pure functions in `core/`; isolate side effects (cache I/O, refresh) and make them injectable for testing.
- **Registries:** Registries are the only place concrete implementations are wired; never import a concrete implementation directly from shared code.
- **Error Handling:** Define typed exceptions in `core/`; adapters translate these to MCP/HTTP error shapes.
- **Security:** Secrets/credentials must never be logged. Redact secret-flagged Terraform attributes before returning a model.
- **Commits:** Conventional commits; small, behavior-scoped commits that pair a test with its implementation.

## Architecture Decisions (ADRs)
Key decisions recorded here for quick reference. Full rationale in `gcp-cost-estimator-server-architecture.md` §7.

- **ADR-009 — Rule-based machine type resolver.** `resolve_machine_type_specs()` derives `(vcpu, ram_gb)` from GCP naming conventions (`{family}-{subtype}-{N}`) rather than a static lookup table. Three-layer chain: rule engine → shared-core overrides → custom machine type pattern. New GCP machine families are handled automatically with zero code change. Cloud SQL has an analogous `resolve_sql_tier_specs()` that strips the `db-` prefix and delegates to the same rule engine for standard tiers, plus a `db-custom-{N}-{M}` fast path.

- **ADR-010 — Cloud SQL Enterprise Plus supports all DB engines.** As of August 2024 (GA), Enterprise Plus supports MySQL, PostgreSQL, and SQL Server. The earlier constraint "Enterprise Plus excludes SQL Server" in the architecture doc is **superseded**. The correct constraint is: Enterprise Plus SQL Server requires an *Enterprise* SQL Server licence version (`SQLSERVER_*_ENTERPRISE`); Standard/Web/Express licence versions are Enterprise edition only. Any code or test asserting the old exclusion is a bug. Source: https://docs.cloud.google.com/sql/docs/sqlserver/editions-intro

- **ADR-011 — 90% spend coverage target via `services.md`.**
- **ADR-014 — Representative defaults over zero-defaults; working estimate over perfect estimate.** When usage fields are absent (size, query volume, egress, etc.), apply a documented representative default rather than zero. Zero-defaults produce misleadingly cheap estimates. Every default is recorded in `assumptions[]` with its value. Billing dimensions not yet fully modelled are surfaced as `unpriced[]` with a reason — never silently dropped. A "known simplifications" backlog in each plan file tracks what needs improving. See `catalog://defaults` for the full defaults catalog.
- **ADR-013 — `export_estimate` writes files server-side.** Server writes to the caller-supplied path (works for all flows including CI/HTTP with no host LLM). Path sanitisation + `EXPORT_ALLOWED_DIR` validation required in the adapter before any write. `core/` contains no filesystem logic. Tool returns the resolved absolute path on success.
- **ADR-012 — NL extraction via schema + prompt + validation only; no server-side heuristic.** Host LLM uses `schema://resource-model` + `estimate-from-description` prompt; server validates and returns structured errors for self-correction. No `extract_resources` heuristic inside the server — that violates ADR-001. Improvements to NL quality go into the prompt/schema, not `core/`. The service implementation roadmap is tracked in `services.md`. Tier 1 (Compute Engine, Cloud Storage, GKE, Cloud SQL, BigQuery) covers ~60% of typical spend. After Tier 1, the recommended order is Cloud Run → Cloud Functions → Cloud Spanner → Firestore → Memorystore.

- **ADR-014 — Dynamic Registry-Driven Billing Services Catalog.** SkuMapper classes declare required billing service display names via `get_supported_billing_services()`. Cache refresh logic queries the GCP Catalog services API, populates a local `billing_services` SQLite table, and resolves required service IDs dynamically from the database. This decouples the loading code from specific service IDs, avoiding modifications to core caching files when new provider services are added.


## Agent Guardrails & Guidelines
- **Do not invent SKUs, prices, machine-type specs, or regions:** If it is not in the cache/fixtures, surface it as unpriced/unknown.
- **Do not invent service billing rules:** Fetch the official pricing page (linked in `services.md`) before implementing any new service. Cite the URL in fixture comments.
- **Do not skip the failing-test step:** The test is the contract that prevents regression and hallucinated behavior. Write the test first!
- **Do not widen scope:** Keep changes focused on the current task's FR. If you have ideas for improvement, record them in `plan.md` or `plan1.md` open questions.
- **Write fixture-backed tests when unsure:** When unsure about GCP pricing semantics, write a fixture-backed test capturing the assumption and flag it, rather than guessing in code.
- **Keep documents synchronized:** Update the architecture doc, `plan.md`/`plan1.md`, and `services.md` whenever a decision changes.
- **Planning mode:** For any non-trivial feature, consult the relevant plan file (`plan.md` for v1 scope, `plan1.md` for Cloud SQL, `services.md` for new services) before writing code. If the feature isn't in a plan, add it as an open question and get it reviewed first.
