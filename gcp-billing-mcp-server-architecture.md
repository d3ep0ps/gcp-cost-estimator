# GCP Billing MCP Server — Requirements & Architecture

**Status:** v0.4 — multi-service extensibility revision
**Date:** 2026-06-03
**Owner:** Vitaliy

> **What changed from v0.2.** The product is no longer an AI agent with an internal sub-agent fleet. It is a **GCP Billing MCP server**: a deterministic server that exposes pricing, IaC parsing, cost calculation, and reporting as **MCP tools, resources, and prompts**. The "intelligence" (natural-language understanding, planning, narration) is supplied by whatever MCP host connects — Claude Code, Gemini CLI, Antigravity / Antigravity CLI, Cursor, etc. There is **no Google ADK, no orchestrator agent, no LLM inside the server**. This makes the system smaller, fully deterministic/testable, host-agnostic, and cheaper to run.

---

## 1. Purpose & Scope

### 1.1 Problem statement
Estimating GCP infrastructure cost before deployment is slow and requires manual SKU lookups. Developers increasingly work inside MCP-capable agent hosts. The fastest way to deliver value is to give those hosts a **tool** they can call — not to build yet another agent.

### 1.2 Goal
Ship a GCP Billing MCP server that any MCP host can use to: parse infrastructure (Terraform or a host-extracted resource model), resolve live **list prices** from a cached GCP SKU catalog, compute an itemized estimate, compare options, and export results.

### 1.3 Design principles
1. **Deterministic core.** Every tool is pure/deterministic given the cache snapshot. Same input → same output. No model calls inside the server.
2. **Borrow the host's intelligence.** NL → structured resources is done by the *host LLM*, guided by an MCP **prompt** + the resource-model **schema resource** we publish. The server validates, it doesn't infer.
3. **Library-first.** All logic lives in a transport-agnostic core library; the MCP server (and an optional HTTP service / CLI) are thin adapters.
4. **Extensible by registry.** Cloud providers, IaC formats, and output formats are plugins behind stable interfaces. v1 ships GCP / Terraform / CSV+markdown only.
5. **Transparent.** List price only; every line item traces to a SKU ID + snapshot timestamp; discounts and assumptions are always disclosed.

### 1.4 In scope (v1)
- MCP server exposing **tools**, **resources**, and **prompts** (see §4).
- GCP **core compute/storage/network** coverage: GCE, persistent/SSD disks, GKE (control plane fee + node VMs), Cloud SQL (all editions: Enterprise + Enterprise Plus; all DB versions: MySQL, PostgreSQL, SQL Server — see ADR-010), Cloud Storage, load balancers, network egress (first-tier rate).
- **90% spend coverage target** tracked in `services.md` (Tier 1–6, ~23 services). Implementation order: Compute Engine → Cloud Storage → GKE → Cloud SQL → BigQuery → Cloud Run → Cloud Functions → … See §11 and `services.md`.
- IaC parsing: **Terraform** (plan-first `terraform show -json`, static HCL fallback) behind an `IaCParser` interface.
- Pricing from a **SQLite** cache of the GCP Cloud Billing **Pricing API** + **SKU groups**; refresh every **72h or on request**.
- Currency **USD only**.
- Output renderers: **JSON, CSV, markdown** (XLSX later).
- Transport: **stdio** (local hosts) and optional **HTTP/SSE** with **bearer-token** auth.
- **Local execution** only.

### 1.5 Forward-looking extensibility (interfaces only in v1)
- More IaC: Pulumi, AWS CloudFormation (`IaCParser` registry).
- More clouds: AWS, Azure (`PricingProvider` + `SkuMapper`, provider-tagged model & cache).
- More outputs: XLSX (`OutputRenderer`).

### 1.6 Out of scope (v1)
- Any LLM/agent logic inside the server.
- Discount modeling (SUD/CUD/EDP/negotiated) — list price only, caveated.
- Non-GCP clouds and non-Terraform IaC as *implementations* (interfaces only).
- XLSX output; hosted/multi-tenant deployment; deployment/provisioning; billing-actuals reconciliation.

---

## 2. Consumers & flows

**Primary consumer:** an MCP host with an LLM (Claude Code, Gemini CLI, Antigravity, Antigravity CLI, Cursor).

**Flow A — natural language.** User: *"estimate 3 n2-standard-4 in us-central1, 24/7, 100GB SSD each."* The host LLM reads our `resource-model` schema resource and `estimate-from-description` prompt, produces a structured resource model, calls `validate_resource_model` then `estimate_infrastructure`, and narrates the returned breakdown.

**Flow B — Terraform.** User points at a Terraform dir. Host calls `parse_terraform(path)` → resource model → `estimate_infrastructure`. The server does the deterministic parse; the host just orchestrates tool calls and explains results.

**Flow C — programmatic.** A script/CI calls the optional HTTP service (bearer token) → same core library, no host LLM involved.

---

## 3. Architecture

```
   MCP Hosts (LLM lives here)
 ┌───────────────────────────────────────────────┐
 │ Claude Code · Gemini CLI · Antigravity(+CLI)   │
 │ Cursor · others                                │
 └───────────────┬───────────────────────────────┘
                 │  MCP (stdio / HTTP+SSE, bearer)
                 ▼
 ┌───────────────────────────────────────────────┐
 │              GCP Billing MCP Server            │  ◀── thin adapter
 │   Tools  ·  Resources  ·  Prompts  (see §4)    │
 └───────────────┬───────────────────────────────┘
                 │  in-process calls
                 ▼
 ┌───────────────────────────────────────────────┐
 │                 Core Library                    │
 │  resource model (cloud-neutral) · validation    │
 │  Registries + interfaces:                       │
 │   IaCParser · PricingProvider/SkuMapper ·       │
 │   CostCalculator · OutputRenderer               │
 │  v1 impls: Terraform · GCP · CSV/MD/JSON         │
 └───────┬───────────────────────────────┬─────────┘
         │                               │
         ▼                               ▼
 ┌───────────────────┐         ┌─────────────────────┐
 │  Pricing Cache    │         │  Refresh job (72h /  │
 │  SQLite           │◀────────│  on-demand)          │
 │ provider·sku·price│         │  atomic snapshot swap│
 │ ·group·ts         │         └──────────┬──────────┘
 └───────────────────┘                    ▼
                              ┌─────────────────────────┐
                              │ GCP Cloud Billing        │
                              │ Pricing API / SKU groups │
                              └─────────────────────────┘

 (Optional)  HTTP/CLI adapter ── same Core Library, for CI/scripts.
```

The server is stateless per request except for the shared read-mostly SQLite cache. No business logic in the adapter; everything is in the core library so MCP, HTTP, and CLI share one implementation.

---

## 3.5 Service extension contract

This section is the authoritative guide for adding a new GCP service. Every service follows the same five-touch-point pattern. All five must be complete before a service is considered done.

### Overview

```
New GCP service
      │
      ├─ 1. Validation & normalisation  core/validate.py
      ├─ 2. SKU mapping                 core/pricing/gcp.py  (GcpSkuMapper)
      ├─ 3. Terraform IaC parsing       core/iac/terraform_hcl.py
      │                                 core/iac/terraform_plan.py
      ├─ 4. Coverage catalog            catalog://coverage resource
      └─ 5. Fixtures & tests            tests/fixtures/{service}_skus.json
                                        tests/test_{service}.py  (TDD-as-BDD)
```

### Touch-point 1 — Validation & normalisation (`core/validate.py`)

Add the new `kind` string to the known-kinds set for its `service`. Then implement service-specific validation rules and defaults in `_validate_resource` / `_normalize_resource`:

```python
# Known kinds registry (extend this dict)
_KNOWN_KINDS: dict[str, set[str]] = {
    "compute":  {"gce_instance"},
    "sql":      {"cloud_sql_instance"},
    "storage":  {"gcs_bucket"},
    "container":{"gke_cluster"},
    # add new service → kind mapping here
}

# Normalisation defaults (extend this dict)
_SERVICE_DEFAULTS: dict[str, dict[str, Any]] = {
    "gce_instance":        {"runtime_hours_per_month": 730},
    "cloud_sql_instance":  {"runtime_hours_per_month": 730,
                            "disk_type": "PD_SSD",
                            "availability_type": "ZONAL"},
    # add defaults for new kind here
}
```

Validation rules must cover:
- Required attributes (e.g. `machine_type`, `tier`, `database_version`).
- Constraint combinations that are invalid (e.g. Enterprise Plus SQL Server + non-Enterprise licence).
- Values that are warnings rather than errors (e.g. unknown `database_version` prefix).
- Secret-flagged attributes to redact (any key containing `password`, `secret`, `key`, `token`).

### Touch-point 2 — SKU mapping (`core/pricing/gcp.py`)

`GcpSkuMapper.map_resource_to_skus` dispatches on `resource.kind`. Add a private method `_map_{kind}` and wire it into the dispatch table:

```python
_MAPPER_DISPATCH: dict[str, Callable] = {
    "gce_instance":       "_map_gce_instance",
    "cloud_sql_instance": "_map_cloud_sql",
    # add new kind → method name here
}
```

Each `_map_{kind}` method must:
1. Read all pricing inputs from `resource.attributes` and `resource.usage` — never from hardcoded numbers.
2. Look up SKUs from the SQLite cache by `(service, description_fragment, region)` — never by hardcoded SKU IDs.
3. Return `(mappings, unpriced)` where `mappings` is a list of `{sku_id, unit_price, unit, qty, component}` dicts and `unpriced` contains any component that could not be resolved.
4. Never silently drop a component — if a SKU lookup fails, add to `unpriced[]` with a reason string.
5. Emit all cost-driving multipliers explicitly (e.g. HA doubles compute qty; storage qty is not multiplied).

SKU lookup convention — use description fragments, not hardcoded SKU IDs:

```python
_SKU_DESCRIPTION_KEYS: dict[tuple[str, str], str] = {
    # (service_kind, component) → fragment to match in cache `description` column
    ("cloud_sql_instance", "mysql_ent_vcpu"): "Cloud SQL for MySQL: Enterprise vCPU",
    # add new entries here
}
```

### Touch-point 3 — Terraform IaC parsing

**`core/iac/terraform_hcl.py`** — add the Terraform resource type to the HCL dispatcher:

```python
_HCL_RESOURCE_HANDLERS: dict[str, Callable] = {
    "google_compute_instance":       _parse_gce_instance,
    "google_sql_database_instance":  _parse_cloud_sql_instance,
    # add new Terraform resource type → parser function here
}
```

Each parser function receives the raw HCL resource block dict and returns a `Resource` model. It must:
- Map HCL attribute paths to the canonical `Resource` fields (`attributes`, `usage`, `attached`).
- Flag any `var.*` / `local.*` / dynamic reference as unresolved (add to a returned `unresolved[]` list, not a default value).
- Handle nested blocks (e.g. `settings[0]` in Cloud SQL) by flattening to the attribute mapping.

**`core/iac/terraform_plan.py`** — add the same Terraform resource type to the plan-JSON dispatcher. Plan-JSON has fully resolved values so there are no unresolved references to flag.

**Attribute mapping table** — document the HCL → model field mapping in the plan file for the service (e.g. `plan1.md` §CS-6 for Cloud SQL). This table is the contract between the parser and the mapper.

### Touch-point 4 — Coverage catalog

Update the `catalog://coverage` data (in `mcp/server.py` or a companion data file) to include the new service:

```python
COVERAGE: dict[str, Any] = {
    "cloud_sql": {
        "kinds": ["cloud_sql_instance"],
        "editions": ["ENTERPRISE", "ENTERPRISE_PLUS"],
        "db_versions": ["MYSQL_*", "POSTGRES_*", "SQLSERVER_*"],
        "ha": True,
        "notes": "Enterprise Plus SQL Server requires Enterprise licence version.",
    },
    # add new service entry here
}
```

### Touch-point 5 — Fixtures and tests (TDD-as-BDD)

Every service requires:

| File | Purpose |
|---|---|
| `tests/fixtures/{service}_skus.json` | Static SKU rows seeded into the test DB. Prices sourced from the official GCP pricing page — cite URL + date in a comment. |
| `tests/fixtures/{service}_cost_cases.json` | Hand-computed expected cost outputs. Each case has inputs + `expected_*` fields verified manually. |
| `tests/fixtures/{service}_estimate_golden.json` | Full golden `Estimate` output for the canonical case. |
| `tests/fixtures/terraform/{service}_*.tf` | HCL fixture files for IaC parser tests. |
| `tests/fixtures/terraform/{service}_plan.json` | Plan-JSON fixture for plan-parser tests. |
| `tests/test_{service}.py` | TDD test file following the step structure in the service's plan file. |

**Test coverage required per service:**
- Validation: valid cases, invalid constraint combinations, defaults applied.
- Tier/machine spec resolution: known-answer round-trips.
- SKU mapping: all billable components mapped; HA multiplier; unresolvable tier → `unpriced[]`.
- Cost calculation: hand-computed golden values.
- End-to-end estimate: golden fixture + combined model (service alongside a GCE instance).
- IaC parsing: HCL + plan-JSON, including unresolved variable detection.
- MCP smoke: tool wiring contract tests.

### Documentation verification (mandatory before any fixture)

Before writing a single fixture value, fetch the official pricing page for the service (listed in `services.md`) and verify every billing component, unit name, and HA rule. Cite the source URL and verification date in a comment next to each fixture. Never use training-data memory for prices or SKU semantics.

---

## 4. MCP surface (the product)

MCP exposes three primitive types. We use all three deliberately.

### 4.1 Tools (model-invoked actions)

**Intake & validation**
- `parse_terraform(path, mode="auto")` → resource model. `mode`: `plan` | `hcl` | `auto`. Reports unresolved dynamic values.
- `parse_terraform_plan_json(plan_json)` → resource model. For hosts that already ran `terraform show -json`.
- `validate_resource_model(model)` → `{valid, errors[], warnings[], normalized_model}`. The guardrail for host-LLM-produced models (Flow A).
- `normalize_resource_model(model)` → canonicalized model (regions, machine types, units).

**Pricing & catalog lookup**
- `list_services()` → supported GCP services in the cache.
- `list_regions(service?)` → regions with pricing.
- `list_machine_types(region?, family?)` → machine types + vCPU/RAM specs.
- `get_machine_type_specs(machine_type)` → `{vcpu, memory_gb}`.
- `search_skus(query, service?, region?)` → candidate SKUs (fuzzy).
- `get_sku(sku_id)` → SKU detail + unit price + unit.
- `map_resource_to_skus(resource)` → SKU(s) a resource decomposes into (e.g., VM → vCPU + RAM + disk SKUs); flags unmapped.
- `price_resource(resource)` → priced line items for one resource.

**Estimation**
- `estimate_infrastructure(model, options?)` → full itemized estimate (line items, monthly/hourly totals, unpriced[], assumptions[], snapshot ts, disclaimer). The coarse, one-shot convenience tool that chains map→price→calc.
- `calculate_resource_cost(resource, options?)` → single-resource cost (fine-grained).

**Comparison & advisory (deterministic)**
- `compare_regions(model, regions[])` → same model priced across regions; cheapest highlighted.
- `compare_estimates(estimate_a, estimate_b)` → line-by-line diff (what-if).
- `what_if(model, changes)` → apply structured changes (e.g., runtime hours, machine type, region) and re-estimate.
- `suggest_cheaper_machine_types(resource, constraints?)` → same/greater vCPU+RAM at lower list price (no discount modeling, pure catalog search).
- `find_unpriced(model)` → resources/SKUs that can't be priced, before a full estimate.

**Output**
- `render_estimate(estimate, format)` → `format`: `json` | `csv` | `markdown`. (XLSX later.)
- `export_estimate(estimate, format, path)` → writes a file, returns path. (Optional; respects host file-permission model.)

**Cache / admin**
- `get_cache_status()` → `{provider, last_refreshed_at, age_hours, sku_count, stale: bool}`.
- `refresh_pricing_cache(provider="gcp", force=false)` → triggers refresh (respects 72h cadence unless `force`).

### 4.2 Resources (read-only context the host can pull in)
- `schema://resource-model` — JSON Schema for the canonical resource model. Lets the host LLM produce valid input in Flow A.
- `catalog://coverage` — coverage matrix: which GCP services/resource kinds are supported in v1.
- `catalog://defaults` — the default assumptions catalog (e.g., 730 runtime hours/month, default region policy) so they're transparent and overridable.
- `pricing://snapshot` — current cache metadata (timestamp, age, SKU counts, source URLs).
- `docs://disclaimer` — the standing list-price/no-discount disclaimer text.

### 4.3 Prompts (reusable templates the user/host can invoke)
- `estimate-from-description` — guides the host LLM to extract a resource model from free text using `schema://resource-model`, then call `validate_resource_model` + `estimate_infrastructure`.
- `estimate-from-terraform` — guides the host to call `parse_terraform` then estimate, and to surface unresolved dynamic values as questions.
- `explain-estimate` — turns a raw estimate JSON into a clear, caveated summary.
- `optimize-cost` — walks `suggest_cheaper_machine_types` / `compare_regions` and summarizes savings (list-price only).

> This three-primitive split is the heart of the design: **tools** do deterministic work, **resources** publish the schema/coverage/snapshot so the host produces valid input, and **prompts** package the workflows. The server never needs its own LLM.

---

## 5. Functional Requirements (FR)

**FR-1 — MCP server (Must).** Expose tools, resources, and prompts of §4 over MCP, transport via stdio and optional HTTP/SSE.
**FR-2 — Terraform parsing (Must).** `parse_terraform` plan-first with HCL fallback, via `IaCParser` registry; unresolved dynamics flagged, never silently assumed.
**FR-3 — Resource-model contract (Must).** Publish `schema://resource-model`; `validate_resource_model` enforces it. Cloud-neutral fields (`provider`, `source`, `service`, `kind`, `region`, `attributes`, `usage`).
**FR-4 — Pricing from cache (Must).** All price lookups hit the SQLite cache; SKU mapping is data-driven; unpriced items reported, not dropped.
**FR-5 — Estimation (Must).** `estimate_infrastructure` returns itemized list-price costs, totals, unpriced[], assumptions[], snapshot ts, disclaimer; reproducible per snapshot.
**FR-6 — Comparison/advisory (Should).** `compare_regions`, `compare_estimates`, `what_if`, `suggest_cheaper_machine_types`.
**FR-7 — Output renderers (Must).** JSON, CSV, markdown via `OutputRenderer` registry; XLSX additive later.
**FR-8 — Cache lifecycle (Must).** `get_cache_status` + `refresh_pricing_cache`; auto-refresh every 72h; atomic snapshot swap.
**FR-9 — Catalog introspection (Should).** `list_services/regions/machine_types`, `search_skus`, `get_sku` for discoverability and host grounding.
**FR-10 — Auth on HTTP transport (Should).** Bearer token when HTTP/SSE is enabled; stdio inherits local trust.
**FR-11 — Extensibility seams (Must).** `IaCParser`, `PricingProvider`/`SkuMapper`, `OutputRenderer` registries; GCP/Terraform/CSV+MD/JSON only in v1.

---

## 6. Non-Functional Requirements (NFR)

- **NFR-1 Determinism (Must).** No randomness, no LLM, no network on the hot path; same input + snapshot → identical output.
- **NFR-2 Traceability (Must).** Every line item carries `sku_id` + `snapshot_ts`; no magic numbers.
- **NFR-3 Performance (Should).** Cache lookups sub-100ms/SKU; a ≤50-resource estimate ≤ 2s (server-side, excludes host LLM).
- **NFR-4 Reliability (Must).** Estimates succeed from cache even if the GCP Pricing API is down; refresh failures never corrupt the live snapshot.
- **NFR-5 Maintainability (Must).** Logic only in core library; MCP/HTTP/CLI are thin adapters; SKU mappings data-driven.
- **NFR-6 Extensibility (Must).** No GCP/Terraform/format assumptions leak into shared code paths; resource model expressive enough for AWS/Azure later.
- **NFR-7 Security (Must).** No secrets in logs; redact secret-flagged Terraform attributes before returning models; bearer token for HTTP; respect host file-permission model for `export_estimate`.
- **NFR-8 Observability (Should).** Structured logs, per-tool timing, cache age, unpriced-SKU counts.
- **NFR-9 Tooling (Must).** Python 3.13+, uv, `pyproject.toml`; built on the MCP Python SDK (e.g., FastMCP-style); containerizable.
- **NFR-10 Spec conformance (Must).** Conform to the MCP spec for tools/resources/prompts so any compliant host works.

---

## 7. Key decisions (ADRs)

- **ADR-001 — Product is an MCP server, not an agent.** Borrow host intelligence; server stays deterministic, testable, host-agnostic, cheap. *Consequence:* NL quality depends on the host LLM; we mitigate with a published schema + prompts + strict validation.
- **ADR-002 — Library-first.** Core library holds all logic; MCP/HTTP/CLI are adapters. *Consequence:* discipline to keep adapters thin.
- **ADR-003 — SQLite cache + 72h/on-demand refresh, atomic swap.** Speed, resilience, reproducibility. *Consequence:* estimates show snapshot age; staleness surfaced.
- **ADR-004 — List price only, caveated.** Simplicity/transparency; discounts are a v2 extension point.
- **ADR-005 — Terraform plan-first + HCL fallback, via `IaCParser` registry.** Accuracy with a no-binary fallback; pluggable for Pulumi/CloudFormation later.
- **ADR-006 — Provider/IaC/output abstraction now, GCP-only impls.** Ready for AWS/Azure/Pulumi/CFN without speculative code.
- **ADR-007 — Use all three MCP primitives.** Tools (deterministic actions), Resources (schema/coverage/snapshot for grounding), Prompts (packaged workflows). This is what removes the need for an in-server LLM.
- **ADR-008 — Python 3.13+ / uv / MCP Python SDK.**
- **ADR-009 — Rule-based machine type resolver.** `resolve_machine_type_specs()` derives `(vcpu, ram_gb)` from GCP naming conventions (`{family}-{subtype}-{N}`) rather than a static lookup table. Three-layer resolution chain: (1) rule engine — handles all standard families automatically, including future ones added by Google; (2) static shared-core overrides for the small set of irregular types (`e2-micro`, `f1-micro`, etc.); (3) custom machine type pattern (`custom-N-MMMM`, `{family}-custom-N-MMMM`). Cloud SQL has an analogous `resolve_sql_tier_specs()` that strips the `db-` prefix and delegates to the same rule engine, plus a `db-custom-{N}-{M}` fast path. *Consequence:* new GCP machine families require zero code change.
- **ADR-010 — Cloud SQL Enterprise Plus supports all DB engines.** As of August 2024 (GA), Enterprise Plus supports MySQL, PostgreSQL, and SQL Server. The earlier constraint "Enterprise Plus excludes SQL Server" is **superseded**. The correct constraint is narrower: Enterprise Plus SQL Server requires an *Enterprise* SQL Server licence version (i.e. `database_version` must end with `_ENTERPRISE`). Standard, Web, and Express licence versions are Cloud SQL Enterprise edition only. Source: https://docs.cloud.google.com/sql/docs/sqlserver/editions-intro. *Any code or test asserting the old blanket exclusion is a bug.*
- **ADR-014 — Representative defaults over zero-defaults; working estimate over perfect estimate.** Users often don't know exact sizing (data volume, query rate, egress) at design time. When a usage field is absent, the server applies a documented representative default rather than defaulting to zero. Zero-defaults produce a misleadingly cheap estimate; representative defaults produce a useful ballpark with full transparency. Every applied default is recorded in `assumptions[]` with its value and a note that it should be overridden when real sizing is known. The `catalog://defaults` resource publishes all defaults so they are auditable. A "known simplifications" backlog is maintained per service (in the plan files) to track billing dimensions not yet fully modelled — these are surfaced as `unpriced[]` items with a reason rather than silently dropped. *Consequence:* estimates are always opinionated and clearly labelled, never silent or zero. Accuracy improves iteratively as simplifications are resolved.
- **ADR-013 — `export_estimate` writes files server-side (Option B).** The server writes the rendered estimate directly to the caller-supplied path rather than returning text for the host to write. Rationale: the only option that works for all three flows, including Flow C (CI/HTTP, no host LLM). *Constraints:* path sanitisation and allowed-directory validation required in the adapter before any write; `core/` contains no filesystem logic; the tool returns the resolved absolute path on success. *Consequence:* the adapter requires a configurable `EXPORT_ALLOWED_DIR` setting; writes outside that directory are rejected with a typed error.
- **ADR-012 — NL extraction via schema + prompt + validation only; no server-side heuristic.** The host LLM uses `schema://resource-model` + `estimate-from-description` prompt to produce the resource model; the server validates and returns structured errors so the host can self-correct. No `extract_resources` heuristic will be built inside the server — that would violate ADR-001 (borrow the host's intelligence) and introduce non-determinism. *Consequence:* NL extraction quality is a function of the host LLM + prompt quality, not server code. Improvements go into the prompt/schema, not `core/`.
- **ADR-011 — 90% GCP spend coverage target, tracked in `services.md`.** The service implementation roadmap is `services.md`. Six tiers, ~23 services total, projected ~97% coverage at completion. Tier 1 (Compute Engine, Cloud Storage, GKE, Cloud SQL, BigQuery) covers ~60% of typical spend and is the first priority. After Tier 1: Cloud Run → Cloud Functions → Cloud Spanner → Firestore → Memorystore. All new service implementations must follow the service extension contract defined in §3.5. *Consequence:* `services.md` is a living document — update it when a service moves from planned → in-progress → done.
- **ADR-014 — Dynamic Registry-Driven Billing Services Catalog.** Rather than hardcoding provider service IDs in the caching module (`gcp_fetch.py`), `SkuMapper` registry classes declare the display names they require via `get_supported_billing_services()`. During cache refreshes, the server downloads the complete GCP services list, updates a local `billing_services` SQLite table, and dynamically queries this table to resolve service IDs. *Consequence:* new cloud services can be supported and priced without modifying any files in the caching/fetch modules.


---

## 8. Canonical resource model (sketch)
```jsonc
{
  "provider": "gcp",                 // cloud-neutral
  "source": "terraform",             // nl | terraform | pulumi | cloudformation
  "resource_id": "vm-1",
  "service": "compute",
  "kind": "gce_instance",
  "region": "us-central1",
  "attributes": { "machine_type": "n2-standard-4" },
  "usage": { "runtime_hours_per_month": 730 },
  "attached": [ { "kind": "ssd_persistent_disk", "size_gb": 100, "quantity": 3 } ],
  "quantity": 3,
  "assumptions": ["runtime defaulted to 730h"]
}
```

## 9. Estimate output (sketch)
```jsonc
{
  "currency": "USD",
  "pricing_snapshot": "2026-06-01T00:00:00Z",
  "disclaimer": "List price only. SUD/CUD/negotiated discounts NOT applied.",
  "line_items": [
    { "resource_id": "vm-1", "sku_id": "...", "component": "vcpu",
      "unit_price": 0.0, "unit": "hour", "qty": 3, "usage_hours": 730,
      "monthly_cost": 0.0 }
  ],
  "monthly_total": 0.0,
  "unpriced": [],
  "assumptions": ["..."]
}
```

---

## 10. Repo layout
```
gcp-billing-mcp/
├─ pyproject.toml                    # uv-managed, py3.13+
├─ CLAUDE.md / GEMINI.md             # agent instructions (keep in sync)
├─ plan.md                           # v1 milestone plan (Milestones 0–8, done)
├─ plan1.md                          # Cloud SQL extension plan (CS-1–CS-10, active)
├─ services.md                       # 90% coverage service roadmap
├─ src/gcp_billing_mcp/
│  ├─ core/                          # ALL business logic lives here
│  │  ├─ model.py                    # Resource / ResourceModel / AttachedResource
│  │  ├─ registries.py               # IaCParser, SkuMapper, OutputRenderer registries
│  │  ├─ validate.py                 # validate_resource_model, normalize_resource_model
│  │  ├─ estimate.py                 # Estimate, PricedLineItem, UnpricedItem models
│  │  ├─ calc.py                     # calculate_line_items, calculate_totals
│  │  ├─ service.py                  # estimate_infrastructure (orchestration)
│  │  ├─ compare.py                  # compare_regions, compare_estimates, what_if, suggest_*
│  │  ├─ logging.py                  # structured logging setup
│  │  ├─ iac/
│  │  │  ├─ base.py                  # IaCParser interface
│  │  │  ├─ terraform_hcl.py         # static HCL parser (python-hcl2)
│  │  │  └─ terraform_plan.py        # terraform show -json parser + auto-mode dispatch
│  │  ├─ pricing/
│  │  │  ├─ gcp.py                   # GcpSkuMapper + resolve_machine_type_specs
│  │  │  ├─ gcp_fetch.py             # GCP Pricing API refresh (injectable transport)
│  │  │  └─ cache.py                 # SQLite cache + atomic swap + get_cache_status
│  │  └─ render/
│  │     ├─ json.py                  # JSON OutputRenderer
│  │     ├─ csv.py                   # CSV OutputRenderer
│  │     └─ markdown.py              # Markdown OutputRenderer
│  ├─ mcp/server.py                  # MCP adapter — thin wrappers only, no logic
│  ├─ http/app.py                    # optional bearer-auth HTTP/SSE adapter
│  └─ cli.py                         # optional CLI adapter
└─ tests/
   ├─ conftest.py                     # autouse network-block fixture, temp DB helpers
   ├─ fixtures/                       # known-answer data — never generated from code
   │  ├─ {service}_skus.json          # static SKU rows per service (cite price source)
   │  ├─ {service}_cost_cases.json    # hand-computed expected costs
   │  ├─ {service}_estimate_golden.json
   │  └─ terraform/                   # .tf and plan.json fixtures per service
   └─ test_*.py                       # one file per module; mirror src/ layout
```

---

## 11. Roadmap

### Completed (Milestones 0–8, per `plan.md` + Cloud SQL extension)
- ✅ Project scaffold, test harness, network-block fixture
- ✅ Canonical resource model + JSON Schema + `schema://resource-model`
- ✅ Validation, normalisation, defaults, secret redaction
- ✅ Estimate + line item + unpriced models
- ✅ SQLite pricing cache + atomic swap + `get_cache_status`
- ✅ GCP price fetcher (injectable transport, 72h cadence)
- ✅ SKU mapping: GCE (vCPU, RAM, persistent disk, egress)
- ✅ Cloud SQL full coverage: all editions, engines, HA, licenses, and backup mapping
- ✅ CostCalculator (known-answer fixtures)
- ✅ `estimate_infrastructure` orchestration
- ✅ Terraform HCL + plan-JSON parsing (`IaCParser` registry)
- ✅ JSON / CSV / Markdown renderers (`OutputRenderer` registry)
- ✅ MCP adapter: all tools, resources, and prompts wired over stdio
- ✅ HTTP/SSE adapter with bearer-token auth
- ✅ Comparison & advisory tools (`compare_regions`, `what_if`, `suggest_cheaper_machine_types`)
- ✅ Structured logging, per-tool timing, staleness UX

### Planned — 90% spend coverage (see `services.md` for priority order)
**Tier 1 remaining**
- BigQuery (storage + on-demand query + streaming inserts)

**Tier 2 — Serverless & containers**
- Cloud Run (vCPU-seconds, memory-seconds, requests)
- Cloud Functions (invocations + compute time)
- App Engine (standard + flexible)

**Tier 3 — Databases**
- Cloud Spanner (processing units, storage)
- Firestore (reads, writes, deletes, storage)
- Memorystore / Redis (capacity-based)
- Bigtable (nodes + storage)
- AlloyDB for PostgreSQL

**Tier 4 — Networking**
- Cloud CDN, Cloud DNS, Cloud NAT, Cloud Armor
- VPC static IPs, VPN, Interconnect

**Tier 5 — Data & analytics**
- Pub/Sub, Dataflow, Dataproc

**Tier 6 — Storage & AI**
- Filestore, Vertex AI, Artifact Registry

### Deferred (v2)
- Discount modeling (SUD/CUD/EDP/negotiated)
- Second IaC parser (Pulumi/CloudFormation)
- Second cloud (AWS/Azure) — interfaces are ready
- XLSX renderer
- Hosted/multi-tenant deployment

---

## 12. References (authoritative GCP Billing sources)
- Cloud Billing Pricing API (REST): https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest
- GCP SKU groups: https://cloud.google.com/skus/sku-groups
- GCP product pricing list (all services): https://cloud.google.com/pricing/list
- Per-service pricing links: see `services.md` (authoritative list)

All pricing/SKU behavior in this server derives from these sources. The pricing cache (§3, FR-4/FR-8) is populated from them; line items trace back to their SKU IDs. **Never use training-data memory for prices, units, or SKU IDs — always verify against the live documentation and cite the source URL + date in fixture comments.**

## 13. Open questions

Resolved questions are kept for history.

1. **NL extraction reliability** — ✅ **Resolved:** schema + prompt + `validate_resource_model` is sufficient. The host LLM reads `schema://resource-model` and the `estimate-from-description` prompt, produces a structured model, and the server validates it strictly. No deterministic `extract_resources` heuristic fallback will be built. Rationale: a fallback heuristic would duplicate host-LLM intelligence inside the server, violating ADR-001 (borrow the host's intelligence). If extraction quality is poor, the fix is a better prompt or schema — not server-side NL parsing. Any validation errors are returned to the host as structured feedback so it can self-correct.

2. **GKE/Cloud SQL granularity** — ✅ **Resolved:**
   - GKE = control plane fee (per-cluster flat fee) + node VMs (vCPU + RAM + disk × `node_count`).
   - Cloud SQL = all editions (Enterprise, Enterprise Plus) × all DB versions (MySQL, PostgreSQL, SQL Server). See ADR-010 for the Enterprise Plus SQL Server licence constraint.

3. **`export_estimate` file access** — ✅ **Resolved (Option B):** The server writes the file directly to the caller-supplied path. Rationale: the only approach that works for all three flows, including Flow C (CI/HTTP with no host LLM). The filesystem side effect is isolated to the MCP/HTTP adapter layer (ADR-002 compliant); `core/` remains purely functional. Implementation constraints: path must be sanitised and validated against a configurable allowed-directory before writing; the tool returns the resolved absolute path on success. See ADR-013.

4. **Terraform prerequisites** — handling configs that need `terraform init`/provider auth before a plan exists; document the HCL-fallback boundary.

5. **Catalog size** — validate SQLite performance/size against the full ~23-service SKU set (see `services.md`).

6. **Coarse vs fine tools** — confirm the mix (keep both `estimate_infrastructure` and the granular `calculate_resource_cost` tool, or trim?).

7. **Service validation registry** — currently validation rules for each service kind are encoded inline in `validate.py`. As services grow toward the 90% target, consider extracting per-kind validators into a registry (analogous to `SkuMapper`) so each service is fully self-contained. Evaluate at Tier 2 completion.

8. **Read replicas (Cloud SQL)** — a `google_sql_database_instance` with `master_instance_name` set is a replica (compute + storage, no HA multiplier). Decide whether replica detection is in scope for `plan1.md` or a follow-up..
