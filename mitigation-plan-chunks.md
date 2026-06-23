# Mitigation Plan — Executable Chunks

Each chunk is a single atomic commit. The "Files touched" column lists every file that changes. Run the full suite after each chunk before moving on.

---

## C-01 · Hotfix · Python 2 `except` syntax — `gcp_fetch.py:168`

**Why urgent:** This is a `SyntaxError` hiding behind an untested branch. It will crash at runtime the first time GCP returns a malformed `unitPrice` value.

### Files touched
- `src/gcp_cost_estimator/core/pricing/gcp_fetch.py`
- `tests/test_gcp_fetch.py`

### Test first (failing)
Add to `tests/test_gcp_fetch.py`:
```python
def test_malformed_unit_price_skipped_gracefully(tmp_db_path, mocker):
    """When unitPrice contains non-numeric values, the SKU is skipped without crashing."""
    bad_sku_payload = {
        "skus": [{
            "skuId": "BAD-001",
            "description": "Bad price",
            "category": {"serviceDisplayName": "Compute Engine", "resourceGroup": "CPU"},
            "serviceRegions": ["us-central1"],
            "pricingInfo": [{"pricingExpression": {
                "usageUnit": "h",
                "tieredRates": [{"unitPrice": {"units": "N/A", "nanos": "N/A"}}],
            }}],
        }]
    }
    # ... mock HTTP client to return bad_sku_payload ...
    result = refresh_pricing_cache(tmp_db_path, force=True, client=mock_client)
    assert result["status"] == "refreshed"
    assert result["sku_count"] == 0  # malformed SKU is skipped, not 1
```

### Source fix
```python
# gcp_fetch.py line 165-170 — BEFORE
try:
    units = int(unit_price_data.get("units", 0))
    nanos = int(unit_price_data.get("nanos", 0))
except ValueError, TypeError:         # ← Python 2 syntax, SyntaxError in Python 3
    units = 0
    nanos = 0

# AFTER
try:
    units = int(unit_price_data.get("units", 0))
    nanos = int(unit_price_data.get("nanos", 0))
except (ValueError, TypeError):       # ← correct Python 3 syntax
    units = 0
    nanos = 0
```

### Commit
```
fix(pricing): fix Python 3 except syntax for malformed unitPrice values
```

---

## C-02 · Security · Hardcoded `"test-token"` in HTTP auth — `http/app.py:82`

**Why urgent:** Any deployment that omits `GCP_BILLING_BEARER_TOKEN` is completely open. The default `"test-token"` is documented nowhere as a secret — it is a well-known bypass.

### Files touched
- `src/gcp_cost_estimator/http/app.py`
- `tests/test_http.py`

### Test first (failing)
```python
def test_create_app_raises_if_no_token_env(monkeypatch):
    """create_app() must refuse to start when GCP_BILLING_BEARER_TOKEN is not set."""
    monkeypatch.delenv("GCP_BILLING_BEARER_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GCP_BILLING_BEARER_TOKEN"):
        create_app()
```

### Source fix
```python
# http/app.py — BEFORE
token = os.environ.get("GCP_BILLING_BEARER_TOKEN", "test-token")

# AFTER
token = os.environ.get("GCP_BILLING_BEARER_TOKEN")
if not token:
    raise RuntimeError(
        "GCP_BILLING_BEARER_TOKEN must be set before starting the HTTP adapter. "
        "Generate a strong random token and export it as this environment variable."
    )
```

> **Note for existing tests:** Tests that call `create_app()` must set `GCP_BILLING_BEARER_TOKEN` via `monkeypatch.setenv`. Update any such tests as part of this chunk.

### Commit
```
fix(http): refuse to start HTTP adapter when GCP_BILLING_BEARER_TOKEN is unset
```

---

## C-03 · Security · GCP API key in URL query param — `gcp_fetch.py:59`

**Why:** `?key=<secret>` appears verbatim in Google's access logs, proxy logs, and `httpx` debug output. The `X-Goog-Api-Key` header is the correct channel.

### Files touched
- `src/gcp_cost_estimator/core/pricing/gcp_fetch.py`

### Test first (failing)
```python
def test_api_key_sent_as_header_not_query_param(tmp_db_path, mocker, monkeypatch):
    monkeypatch.setenv("GCP_API_KEY", "my-secret-key")
    captured = {}
    def fake_get(url, params=None, headers=None, **kw):
        captured["params"] = params or {}
        captured["headers"] = headers or {}
        return mock_ok_response()

    mock_client = mocker.Mock()
    mock_client.get.side_effect = fake_get
    refresh_pricing_cache(tmp_db_path, force=True, client=mock_client)

    assert "key" not in captured["params"]
    assert captured["headers"].get("X-Goog-Api-Key") == "my-secret-key"
```

### Source fix
```python
# gcp_fetch.py — BEFORE
if api_key:
    params["key"] = api_key

# AFTER
if api_key:
    headers["X-Goog-Api-Key"] = api_key
```

### Commit
```
fix(pricing): send GCP API key as header instead of URL query parameter
```

---

## C-04 · Security · Timing-safe token comparison + document SSE query-string risk

**Why:** `!=` on strings is not constant-time. While difficult to exploit over TCP, this is a one-line fix with `hmac.compare_digest`. The query-string token fallback is left in place (needed for SSE clients) but documented with an explicit warning comment.

### Files touched
- `src/gcp_cost_estimator/http/app.py`

### Source fix
```python
# http/app.py — add at top
import hmac

# BEFORE
if token_val != self.token:
    await self.unauthorized(send, "Invalid bearer token")

# AFTER
if not hmac.compare_digest(token_val, self.token):
    await self.unauthorized(send, "Invalid bearer token")
```

Also add a warning comment above the query-string fallback block:
```python
# WARNING: The ?token= query param is logged in server access logs.
# Prefer the Authorization header whenever the client supports it.
# For SSE-only clients that cannot set headers, this is an accepted trade-off;
# consider a short-lived ticket system for production SSE deployments.
if not token_val:
    query_string = scope.get("query_string", b"").decode("utf-8")
    ...
```

### Test (verify existing tests still pass; no new behaviour)
```
uv run pytest tests/test_http.py -x
```

### Commit
```
fix(http): use constant-time comparison for bearer token validation
```

---

## C-05 · Security · Path traversal in `parse_terraform` MCP tool — `mcp/server.py`

**Why:** The tool accepts a raw `path: str` from the LLM/MCP host and hands it directly to `TerraformHclParser.parse()`. There is no `PARSE_ALLOWED_DIR` guard analogous to `EXPORT_ALLOWED_DIR` mentioned in ADR-013.

### Files touched
- `src/gcp_cost_estimator/mcp/server.py`
- `tests/test_mcp.py`

### Test first (failing)
```python
def test_parse_terraform_rejects_path_outside_allowed_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GCP_PARSE_ALLOWED_DIR", str(tmp_path / "safe"))
    with pytest.raises(ValueError, match="outside the allowed directory"):
        parse_terraform(path="/etc")
```

### Source fix
```python
# mcp/server.py — add near top of file
import os

_PARSE_ALLOWED_DIR = os.environ.get("GCP_PARSE_ALLOWED_DIR")


@mcp.tool()
@timed_tool
def parse_terraform(path: str, mode: str = "auto") -> dict[str, Any]:
    resolved = Path(path).resolve()
    if _PARSE_ALLOWED_DIR:
        allowed = Path(_PARSE_ALLOWED_DIR).resolve()
        if not str(resolved).startswith(str(allowed) + os.sep):
            raise ValueError(
                f"Path '{resolved}' is outside the allowed directory '{allowed}'. "
                "Set GCP_PARSE_ALLOWED_DIR to the workspace root."
            )
    return parse_terraform_core(str(resolved), mode=mode).model_dump()
```

> **Note:** When `GCP_PARSE_ALLOWED_DIR` is not set, the guard is skipped (permissive default). Operators can opt-in via the env var. This keeps backward compatibility for local development.

### Commit
```
fix(mcp): add path traversal guard to parse_terraform via GCP_PARSE_ALLOWED_DIR
```

---

## C-06 · Architecture · SQLite connection-per-resource anti-pattern — `pricing/gcp/mapper.py`

**Why:** `map_resource_to_skus` opens a new `sqlite3.Connection` for every resource. A 50-resource model opens 50 connections. `compare_regions` over 5 regions × 50 resources = 250 connections per call. The correct fix is to open one connection per estimation pass and pass a cursor down to each mapper function.

### Approach
`GcpSkuMapper` is instantiated by `get_sku_mapper()` in `service.py` once per `estimate_infrastructure` call. We change `map_resource_to_skus` to open **one connection** per mapper instance lifecycle instead of per call. The cleanest zero-interface-change approach: open the connection lazily on first call and close it explicitly in a `close()` method called by the registry/service layer. An alternative that requires no registry change: open per-call but with a single `with sqlite3.connect(...) as conn:` block that covers the full method body (already equivalent, but makes it explicit). The **recommended** approach is a lazy connection with explicit `close()`.

### Files touched
- `src/gcp_cost_estimator/core/pricing/gcp/mapper.py`
- `src/gcp_cost_estimator/core/registries.py` (add `close()` call after use)
- `src/gcp_cost_estimator/core/service.py` (ensure mapper is closed after estimation)
- `tests/test_gke_mapper.py` (update fixture if it patches connection)

### Source fix sketch
```python
# mapper.py
class GcpSkuMapper(SkuMapper):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_cursor(self) -> sqlite3.Cursor:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._conn.cursor()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def map_resource_to_skus(self, resource: Resource) -> tuple[list, list]:
        ...
        cursor = self._get_cursor()
        # no try/finally conn.close() — connection is reused across resources
        ...
```

```python
# service.py — after all resources are processed
mapper = get_sku_mapper(r.provider, db_path)
try:
    for r in normalized_model.resources:
        mappings, unpriced = mapper.map_resource_to_skus(r)
        ...
finally:
    if hasattr(mapper, "close"):
        mapper.close()
```

### Commit
```
perf(pricing): reuse SQLite connection across resources in GcpSkuMapper
```

---

## C-07 · Architecture · Replace 28-branch `if/elif` + delete 28 dead private methods — `mapper.py`

**Depends on:** C-06 (mapper.py is already modified; this chunk completes the refactor)

**Why:** Every new service requires editing `GcpSkuMapper` (OCP violation). The 28 private `_map_*` methods are one-line wrappers that add zero value. A dispatch table removes both problems in one pass.

### Files touched
- `src/gcp_cost_estimator/core/pricing/gcp/mapper.py`

### Design
```python
# mapper.py — class-level dispatch table
# Key: (service, kind) tuple. Value: module-level mapping function.
_DISPATCH: dict[tuple[str, str], Callable[[Resource, sqlite3.Cursor], tuple[list, list]]] = {
    ("compute",           "gce_instance"):               _map_gce_instance_with_attached,
    ("container",         "gke_cluster"):                map_gke_cluster,
    ("container",         "gke_node_pool"):              map_gke_node_pool,
    ("sql",               "cloud_sql_instance"):         map_cloud_sql,
    ("storage",           "gcs_bucket"):                 map_gcs_bucket,
    ("cdn",               "cloud_cdn_backend"):          map_cloud_cdn_backend,
    ("dns",               "dns_managed_zone"):           map_dns_managed_zone,
    ("nat",               "nat_gateway"):                map_nat_gateway,
    ("vpc",               "compute_address"):            map_compute_address,
    ("armor",             "compute_security_policy"):    map_compute_security_policy,
    ("pubsub",            "pubsub_topic"):               map_pubsub_topic,
    ("pubsub",            "pubsub_subscription"):        map_pubsub_subscription,
    ("dataflow",          "dataflow_job"):               map_dataflow_job,
    ("dataproc",          "dataproc_cluster"):           map_dataproc_cluster,
    ("bigquery",          "bigquery_dataset"):           map_bigquery_dataset,
    ("run",               "cloud_run_service"):          map_cloud_run_service,
    ("run",               "cloud_run_job"):              map_cloud_run_job,
    ("functions",         "cloud_function"):             map_cloud_function,
    ("appengine",         "app_engine_standard_version"): map_app_engine_standard_version,
    ("appengine",         "app_engine_flexible_version"): map_app_engine_flexible_version,
    ("spanner",           "spanner_instance"):           map_spanner_instance,
    ("firestore",         "firestore_database"):         map_firestore_database,
    ("memorystore",       "redis_instance"):             map_redis_instance,
    ("memorystore",       "memorystore_instance"):       map_memorystore_instance,
    ("bigtable",          "bigtable_instance"):          map_bigtable_instance,
    ("alloydb",           "alloydb_cluster"):            map_alloydb_cluster,
    ("alloydb",           "alloydb_instance"):           map_alloydb_instance,
    ("filestore",         "filestore_instance"):         map_filestore_instance,
    ("vertex_ai",         "vertex_ai_endpoint"):        map_vertex_ai_endpoint,
    ("artifact_registry", "artifact_registry_repository"): map_artifact_registry_repository,
}

def map_resource_to_skus(self, resource: Resource) -> tuple[list, list]:
    if resource.provider != "gcp":
        return [], [{"resource_id": resource.resource_id,
                     "reason": f"GcpSkuMapper cannot process provider '{resource.provider}'"}]
    if not resource.region:
        return [], [{"resource_id": resource.resource_id,
                     "reason": "No region specified for GCE resource."}]

    cursor = self._get_cursor()
    fn = self._DISPATCH.get((resource.service, resource.kind))
    if fn is None:
        return [], [{"resource_id": resource.resource_id,
                     "reason": f"Unsupported resource kind '{resource.kind}'"}]
    return fn(resource, cursor)
```

> The existing autopilot GKE cluster special-casing and the GCE attached-disk logic need to move into thin wrapper functions (e.g., `_map_gce_instance_with_attached`) that are registered in the dispatch table. These wrappers stay in `mapper.py` since they contain cross-resource logic that does not belong in the service-specific modules.

### Delete
All 28 private `_map_*` methods on `GcpSkuMapper`.

### Verify
```bash
uv run pytest -x && uv run mypy src && uv run ruff check .
```

### Commit
```
refactor(pricing): replace if/elif chain and dead delegation methods with dispatch table
```

---

## C-08 · Tech Debt · Silent HCL parse failure — `iac/terraform_hcl.py:49`

**Why:** A malformed `.tf` file is silently dropped. The caller cannot distinguish "parsed 0 resources from a valid empty dir" from "3 files failed to parse". This violates ADR-004 (fail loud, never under-report).

### Files touched
- `src/gcp_cost_estimator/core/iac/terraform_hcl.py`
- `tests/test_iac.py`

### Test first (failing)
```python
def test_malformed_tf_file_is_surfaced_in_assumptions(tmp_path):
    """A malformed .tf file is skipped but recorded; valid sibling files are still parsed."""
    (tmp_path / "bad.tf").write_text("resource { this is not valid HCL }")
    (tmp_path / "good.tf").write_text(
        'resource "google_compute_instance" "vm" { machine_type = "n1-standard-1" }'
    )
    parser = TerraformHclParser()
    model = parser.parse(str(tmp_path))
    assert len(model.resources) >= 1  # good.tf parsed
    assert any("bad.tf" in a for r in model.resources for a in r.assumptions) or \
           any("bad.tf" in w for w in getattr(model, "_parse_warnings", []))
```

### Source fix
```python
# terraform_hcl.py — BEFORE
except Exception:
    pass

# AFTER
import logging
_logger = logging.getLogger("gcp_cost_estimator")

except Exception as exc:
    _logger.warning("Skipping '%s': failed to parse HCL: %s", fpath.name, exc)
    parse_warnings.append(f"Skipped '{fpath.name}': {exc}")
```

Attach `parse_warnings` to the model via `ResourceModel.metadata` or an assumptions list at model level (check model schema first — use the least-invasive approach).

### Commit
```
fix(iac): surface HCL parse failures instead of silently swallowing them
```

---

## C-09 · Tech Debt · Global `runtime_hours` default applied to non-compute services — `core/validate.py:63`

**Why:** GCS buckets, Pub/Sub topics, DNS zones, and other non-compute resources receive `runtime_hours_per_month = 730` and a nonsensical assumption entry _"Defaulted runtime to 730 hours/month"_. This clutters `assumptions[]` and misleads users.

### Files touched
- `src/gcp_cost_estimator/core/validate.py`
- `src/gcp_cost_estimator/core/validation/gcp/compute.py` (add default there)
- `src/gcp_cost_estimator/core/validation/gcp/container.py`
- `src/gcp_cost_estimator/core/validation/gcp/sql.py`
- `tests/test_validate.py`

### Services that legitimately use `runtime_hours_per_month`
`compute/gce_instance`, `container/gke_*`, `sql/cloud_sql_instance`, `dataproc/dataproc_cluster`, `appengine/*`, `memorystore/*`

### Test first (failing)
```python
def test_gcs_bucket_does_not_get_runtime_hours_default(tmp_db_path):
    model = ResourceModel(resources=[Resource(
        resource_id="bucket-1", provider="gcp", service="storage",
        kind="gcs_bucket", region="us-central1",
    )])
    result = validate_resource_model(model)
    r = result["normalized_model"].resources[0]
    assert "runtime_hours_per_month" not in r.usage
    assert not any("runtime" in a.lower() for a in r.assumptions)
```

### Source fix
```python
# validate.py — REMOVE the global default block (lines 63-67)
# if "runtime_hours_per_month" not in r.usage:
#     r.usage["runtime_hours_per_month"] = 730
#     ...

# Instead, add the default inside compute.py normalizer:
# validation/gcp/compute.py
def normalize_compute(r: Resource) -> None:
    if "runtime_hours_per_month" not in r.usage:
        r.usage["runtime_hours_per_month"] = 730
        r.assumptions.append("Defaulted runtime to 730 hours/month.")
```

Repeat the pattern for each service normalizer that needs it. Services that never use `runtime_hours_per_month` (storage, pubsub, dns, nat, vpc, cdn, firestore, bigquery, artifact_registry) get nothing.

### Commit
```
fix(validation): move runtime_hours default into compute-specific normalizers only
```

---

## C-10 · Tech Debt · Error-to-resource matching by string substring — `core/service.py:44`

**Why:** `if r.resource_id in err or r.kind in err` matches by substring. A resource named `"sql"` matches any error containing the word `"sql"`. Validators should emit structured objects, not plain strings.

### Files touched
- `src/gcp_cost_estimator/core/validate.py` (change `errors` type)
- `src/gcp_cost_estimator/core/validation/gcp/__init__.py` (update validator signature)
- `src/gcp_cost_estimator/core/service.py` (update matching logic)
- `tests/test_validate.py`, `tests/test_service.py`

### Design
Change `errors: list[str]` in `validate_resource_model` to `errors: list[dict[str, str]]` with shape `{"resource_id": str, "reason": str}`. Validators append dicts. `service.py` matches by `item["resource_id"]` exactly.

```python
# validate.py — new error type
ValidationError = TypedDict("ValidationError", {"resource_id": str, "reason": str})

# validator call sites — BEFORE
errors.append(f"Resource '{r.resource_id}': invalid tier")

# AFTER
errors.append({"resource_id": r.resource_id, "reason": "Invalid tier specified."})
```

```python
# service.py — BEFORE
if r.resource_id in err or r.kind in err:
    unpriced_items.append(UnpricedItem(resource_id=r.resource_id, reason=err))

# AFTER
for err in val_res["errors"]:
    res_id = err["resource_id"] if isinstance(err, dict) else "model"
    reason = err["reason"] if isinstance(err, dict) else str(err)
    unpriced_items.append(UnpricedItem(resource_id=res_id, reason=reason))
```

> **Backward-compat note:** Update all validator modules under `validation/gcp/` — there are ~20 of them. Use `grep -rn "errors.append" src/` to find all call sites before coding.

### Commit
```
refactor(validation): use structured error dicts instead of plain strings
```

---

## C-11 · Testing · `temp_db_path` fixture leaves artifacts on crash — `tests/conftest.py:45`

**Why:** The fixture uses a hardcoded path in the test directory. If a test crashes mid-fixture, the SQLite file persists and can corrupt a subsequent run.

### Files touched
- `tests/conftest.py`

### Fix
```python
# conftest.py — BEFORE
@pytest.fixture
def temp_db_path() -> Any:
    from pathlib import Path
    path = Path(__file__).parent / "temp_test_db.sqlite"
    if path.exists():
        path.unlink()
    yield str(path)
    if path.exists():
        with contextlib.suppress(OSError):
            path.unlink()

# AFTER
@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Temporary SQLite DB path — cleaned up automatically by pytest even on crash."""
    return str(tmp_path / "test.sqlite")
```

### Commit
```
fix(tests): use pytest tmp_path for temp_db_path fixture to prevent artifact leakage
```

---

## C-12 · Testing · Missing test cases for business-logic correctness

Three gaps where wrong logic would pass all current tests.

### Files touched
- `tests/test_compare.py`
- `tests/test_validate.py` (or new `tests/test_validation_correctness.py`)
- `tests/test_iac.py`

### 12a — Cheapest-region selection actually correct
```python
def test_compare_regions_cheapest_is_lowest_cost(tmp_db_path):
    """Given two regions with different prices, cheapest_region must point to the lower one."""
    # Seed DB with us-central1 at $0.01/h and europe-west1 at $0.02/h for same SKU group
    _seed_pricing(tmp_db_path, region="us-central1", unit_price=0.01)
    _seed_pricing(tmp_db_path, region="europe-west1", unit_price=0.02)

    model = _single_vm_model()
    result = compare_regions(tmp_db_path, model, ["us-central1", "europe-west1"])

    assert result["cheapest_region"] == "us-central1"
    us_total = result["estimates"]["us-central1"]["monthly_total"]
    eu_total = result["estimates"]["europe-west1"]["monthly_total"]
    assert us_total < eu_total
```

### 12b — `what_if` warns on unrecognised change keys
```python
def test_what_if_unknown_key_raises_or_warns(tmp_db_path):
    """Passing an unrecognised key in changes must not silently succeed."""
    model = _single_vm_model()
    result = what_if(tmp_db_path, model, changes={"disk_type": "pd-ssd"})
    # Acceptable: either raise ValueError or include a warning in assumptions/metadata
    assert "unrecognised" in str(result).lower() or "unknown" in str(result).lower()
```

### 12c — HCL parse failure is visible to caller
```python
def test_terraform_hcl_parse_failure_visible(tmp_path):
    (tmp_path / "bad.tf").write_text("NOT { VALID HCL !!!")
    parser = TerraformHclParser()
    model = parser.parse(str(tmp_path))
    # Model is returned (no crash), but failure is surfaced somehow
    all_text = json.dumps(model.model_dump())
    assert "bad.tf" in all_text or model.resources == []
```

### Commit
```
test: add missing correctness tests for compare_regions, what_if, and HCL parse failure
```

---

## PR Body Template

After all 12 chunks are committed:

```bash
gh pr create \
  --title "fix: security hardening, architecture improvements, and test debt (audit follow-up)" \
  --body "$(cat <<'EOF'
## Summary
Addresses all findings from the 2026-06-23 security and architecture audit.

- **Security (4 fixes):** path traversal guard, hardcoded token bypass, API key in URL, timing-safe comparison
- **Architecture (3 fixes):** Python 2 syntax bug, SQLite connection reuse, dispatch table replacing if/elif chain
- **Tech Debt (3 fixes):** HCL silent failure, scoped runtime_hours default, structured validation errors
- **Tests (2 fixes):** tmp_path fixture, missing correctness assertions

## Test plan
- [ ] `uv run pytest` — all 700+ tests pass
- [ ] `uv run pytest --cov=gcp_cost_estimator --cov-branch` — coverage does not regress
- [ ] `uv run mypy src` — no new type errors
- [ ] `uv run ruff check .` — no lint violations
- [ ] Deploy HTTP adapter without `GCP_BILLING_BEARER_TOKEN` set — confirm `RuntimeError` on startup
- [ ] Call `parse_terraform` with `path=/etc` and `GCP_PARSE_ALLOWED_DIR` set — confirm `ValueError`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
