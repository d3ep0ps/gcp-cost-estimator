# Mitigation Plan — Overview

**Branch:** `fix/audit-mitigations`  
**Base:** `main`  
**Strategy:** One micro-commit per chunk. Every commit must leave tests green. No PR is opened until all chunks are merged and CI passes.

## Issues → Chunks Map

| Chunk | Category | Severity | Issue |
|-------|----------|----------|-------|
| [C-01](mitigation-plan-chunk-01.md) | Hotfix | HIGH | Python 2 `except` syntax — latent `SyntaxError` in `gcp_fetch.py` |
| [C-02](mitigation-plan-chunk-02.md) | Security | HIGH | Hardcoded `"test-token"` default in HTTP auth middleware |
| [C-03](mitigation-plan-chunk-03.md) | Security | MEDIUM | GCP API key sent as URL query param (logged in plaintext) |
| [C-04](mitigation-plan-chunk-04.md) | Security | MEDIUM | Token comparison not timing-safe + query-string token exposure |
| [C-05](mitigation-plan-chunk-05.md) | Security | HIGH | Path traversal in `parse_terraform` MCP tool |
| [C-06](mitigation-plan-chunk-06.md) | Architecture | HIGH | Connection-per-resource SQLite anti-pattern in `GcpSkuMapper` |
| [C-07](mitigation-plan-chunk-07.md) | Architecture | HIGH | 28-branch `if/elif` chain + 28 dead private delegation methods |
| [C-08](mitigation-plan-chunk-08.md) | Tech Debt | MEDIUM | Silent exception swallowing in `terraform_hcl.py` |
| [C-09](mitigation-plan-chunk-09.md) | Tech Debt | MEDIUM | Global `runtime_hours` default applied to non-compute services |
| [C-10](mitigation-plan-chunk-10.md) | Tech Debt | MEDIUM | Error-to-resource matching by string substring in `service.py` |
| [C-11](mitigation-plan-chunk-11.md) | Testing | LOW | `temp_db_path` fixture leaves artifacts on crash |
| [C-12](mitigation-plan-chunk-12.md) | Testing | MEDIUM | Missing test cases (cheapest-region, what_if keys, HCL parse fail) |

## Execution Order

Chunks are sequenced to minimise merge conflicts:

```
C-01  →  C-02  →  C-03  →  C-04   (independent hotfixes / security, no shared files)
                                 ↓
                               C-05   (server.py — independent of C-02..04)
                                 ↓
                               C-06   (mapper.py — refactors connection handling)
                                 ↓
                               C-07   (mapper.py — must follow C-06, rewrites dispatch)
                                 ↓
                    C-08  C-09  C-10   (independent tech-debt fixes, can run in any order)
                                 ↓
                         C-11  C-12   (test fixes — depend on all source fixes above)
```

## Definition of Done (per chunk)

- [ ] Failing test written first (where applicable) and now passing.
- [ ] Full suite green: `uv run pytest`
- [ ] Lint + type-check clean: `uv run ruff check . && uv run mypy src`
- [ ] No business logic removed or behaviour changed — only improvement.
- [ ] Commit message follows conventional commits: `fix(scope): description`.

## Branch & PR Commands

```bash
git checkout -b fix/audit-mitigations
# ... implement each chunk, commit after each ...
gh pr create --title "fix: address audit findings — security, arch, and test debt" \
  --body "$(cat pr-body.md)"
```
