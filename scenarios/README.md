# GCP Billing MCP Server — Test Scenarios

This directory contains Terraform configurations designed to verify every major capability of the **GCP Billing MCP Server** when connected to your LLM host (Antigravity, Claude Code, Cursor, Gemini CLI, or any other MCP-capable host).

Each scenario targets a specific behaviour: correct parsing, rule-engine resolution, edge-case handling, unpriced reporting, and advanced tools (`compare_regions`, `what_if`, `suggest_cheaper_machine_types`).

---

## Prerequisite: Reload the MCP Server

If you just registered the MCP server in your `mcp_config.json`, restart your chat/IDE session so the tools are loaded.

Verify it is active:
> "Are the gcp-billing tools loaded?"
> "What MCP servers are connected?"

---

## Quick-reference table

| # | Scenario | Primary capability tested |
|---|---|---|
| 1 | Single GCE VM with SSD boot disk | Basic parse + price |
| 2 | Multiple GCE VMs (`count = 3`) | Static count multiplication |
| 3 | Mixed resources with unpriced items | Fail-loud / unpriced[] reporting (Pub/Sub) |
| 4 | Unresolved Terraform variables | HCL default fallback + assumptions log |
| 5 | Multi-VM, mixed machine families | Multi-resource, family-prefix SKU matching |
| 6 | Preemptible (Spot) VM | Scheduling attribute parsing |
| 7 | Custom machine type (`custom-6-20480`) | Layer-3 rule-engine (MB → GB) |
| 8 | Region comparison baseline | `compare_regions` over 5 regions |
| 9 | Shared-core VMs (e2-micro/small/medium) | Layer-2 static shared-core overrides |
| 10 | Realistic web-app stack (fleet + DB) | Large count, multiple kinds, cost totals |
| 11 | ML workload (N1 highmem + N1 standard) | N1 per-family ratio override (6.5 GB/vCPU) |
| 12 | What-if upgrade baseline | `what_if` / `suggest_cheaper_machine_types` |
| 13 | Highcpu batch fleet (20 nodes) | highcpu subtype (1.0 GB/vCPU), big fleet |
| 14 | Partial failure (unknown machine type) | Unpriced[] with priced item still computed |
| 15 | GKE Cluster & Node Pool | GKE cluster fee, node/boot disk mapping, defaults |
| 16 | BigQuery Dataset and Table | Dataset storage class, query scans, streaming |
| 17 | Combined Tier 1 Stack | Integration across all 5 Tier 1 services |
| 18 | Natural Language Description | Host-side NL extraction, validation, estimation |
| — | Advanced prompts (section at the bottom) | `compare_regions`, `what_if`, cost optimisation |

---

## Scenario 1 — Single GCE VM with SSD Boot Disk

**Path:** `scenarios/scenario_1_single_vm/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_1_single_vm/main.tf)  
**Goal:** Verify parsing and cost calculation of a basic GCE VM with a custom SSD boot disk.

### LLM prompt
> Use the `estimate-from-terraform` prompt on the path `scenarios/scenario_1_single_vm/`.

### Expected results
- **Resources:** 1 × `google_compute_instance.vm_instance`
- **Machine type:** `n2-standard-4` → 4 vCPUs, 16 GB RAM
- **Disk:** 100 GB `pd-ssd`
- **Region:** `us-central1`
- **Cost:** ~$63/month list price
  - vCPU: 4 × $0.0063/vCPU·hr × 730 hr ≈ $18.40
  - RAM: 16 GB × $0.0034/GB·hr × 730 hr ≈ $39.69
  - Disk: 100 GB × $0.0500/GB·month = $5.00

---

## Scenario 2 — Multiple GCE VMs (`count = 3`)

**Path:** `scenarios/scenario_2_multiple_vms/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_2_multiple_vms/main.tf)  
**Goal:** Verify that a static `count` attribute is resolved and the quantity multiplies both compute and disk costs.

### LLM prompt
> Estimate the infrastructure cost of the Terraform folder `scenarios/scenario_2_multiple_vms/`.

### Expected results
- **Resources:** 1 definition × quantity 3
- **Machine type:** `e2-standard-2` → 2 vCPUs, 8 GB RAM per instance
- **Disk:** 50 GB `pd-standard` per instance
- **Region:** `europe-west1`
- **Cost:** ~$146/month for all 3 instances combined
- **Check:** quantity field must be `3` on both the compute and disk line items

---

## Scenario 3 — Mixed Resources with Unpriced Items

**Path:** `scenarios/scenario_3_unpriced_resources/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_3_unpriced_resources/main.tf)  
**Goal:** Confirm the server never silently ignores unsupported resource types — they must appear in the `unpriced[]` list.

### LLM prompt
> Parse and estimate `scenarios/scenario_3_unpriced_resources/`. Identify any unpriced or unsupported resource types.

### Expected results
- **Priced:**
  - `google_compute_instance.db_backup_server` (`e2-medium`, 30 GB `pd-standard`, `us-central1`)
  - `google_storage_bucket.backup_bucket` (`STANDARD` storage, US region, defaults applied)
- **Unpriced (must be listed explicitly):**
  - `google_pubsub_topic.notification_topic`
- **Output:** must show a warning/unpriced section with reasons for the Pub/Sub topic; cost reflects both the VM and the GCS bucket.

---

## Scenario 4 — Unresolved Variables & Assumptions

**Path:** `scenarios/scenario_4_unresolved_vars/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_4_unresolved_vars/main.tf)  
**Goal:** Verify that the HCL parser falls back to defaults for unresolved `var.*` references and records every assumption.

### LLM prompt
> Estimate the cost for `scenarios/scenario_4_unresolved_vars/` and explain what default assumptions were made for unresolved variables.

### Expected results
- **Assumptions listed:**
  - `var.machine_type` → fallback to `e2-medium`
  - `var.disk_size` → fallback to `10` GB
  - `var.node_count` → fallback to `1`
- **Check:** the LLM response should enumerate these assumptions explicitly

---

## Scenario 5 — Multi-VM, Mixed Machine Families

**Path:** `scenarios/scenario_5_multi_vm_mixed_families/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_5_multi_vm_mixed_families/main.tf)  
**Goal:** Verify that three different machine families in the same region each receive the correct family-specific SKU from the cache (family-prefix matching: N1, E2, N2).

### LLM prompt
> Estimate the total monthly cost of `scenarios/scenario_5_multi_vm_mixed_families/` and break down the cost per VM.

### Expected results
- **`api_server`:** `n1-standard-8` → 8 vCPUs, 30 GB RAM (N1 ratio: 3.75 GB/vCPU × 8), 50 GB `pd-ssd`
- **`worker`:** `e2-standard-4` → 4 vCPUs, 16 GB RAM, 200 GB `pd-standard`
- **`cache`:** `n2-highmem-4` → 4 vCPUs, 32 GB RAM (highmem ratio: 8.0 GB/vCPU × 4), 100 GB `pd-ssd`
- **Check:** each VM line item must carry a distinct SKU ID that matches its family

---

## Scenario 6 — Preemptible (Spot) VM

**Path:** `scenarios/scenario_6_preemptible_vm/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_6_preemptible_vm/main.tf)  
**Goal:** Verify that the parser picks up the `scheduling { preemptible = true }` block and that the LLM notes this as a pricing caveat.

### LLM prompt
> Estimate the cost of `scenarios/scenario_6_preemptible_vm/` and explain any pricing caveats.

### Expected results
- **Machine type:** `n2-standard-4` → 4 vCPUs, 16 GB RAM
- **Disk:** 50 GB `pd-standard`
- **Region:** `us-central1`
- **Caveat:** The LLM must note that the instance is **preemptible (Spot)** and that the listed price is the on-demand rate; actual Spot prices are ~60–91% lower but are not guaranteed
- **Cost shown:** on-demand list price (server only returns list prices; discount is documented, not applied)

---

## Scenario 7 — Custom Machine Type

**Path:** `scenarios/scenario_7_custom_machine_type/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_7_custom_machine_type/main.tf)  
**Goal:** Verify that the rule-engine Layer 3 correctly interprets `custom-6-20480` as 6 vCPUs and 20.0 GB RAM (20480 MB ÷ 1024).

### LLM prompt
> Estimate the cost of `scenarios/scenario_7_custom_machine_type/` and confirm the vCPU and RAM values used.

### Expected results
- **Machine type:** `custom-6-20480` → **6 vCPUs**, **20.0 GB RAM**
- **Disk:** 100 GB `pd-ssd`
- **Region:** `us-central1`
- **Check:** the estimate line items must show qty = 6 for vCPU and qty = 20.0 for RAM; no unpriced entry for this VM

---

## Scenario 8 — Region Comparison Baseline

**Path:** `scenarios/scenario_8_region_comparison/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_8_region_comparison/main.tf)  
**Goal:** Price an identical `n2-standard-4` + 100 GB SSD workload across five regions and identify the cheapest.

### LLM prompt
> Compare the cost of `scenarios/scenario_8_region_comparison/main.tf` across `us-central1`, `us-east1`, `europe-west1`, `europe-west4`, and `asia-east1`. Which region is cheapest?

### Expected results
- The LLM calls `compare_regions` with all five region strings
- Returns a ranked table of monthly cost per region
- Identifies the cheapest region (typically `us-central1` or `us-east1` for N2)
- **Check:** each region must show a separate cost; the cheapest region must be explicitly called out

---

## Scenario 9 — Shared-Core VMs (e2-micro / e2-small / e2-medium)

**Path:** `scenarios/scenario_9_shared_core_vms/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_9_shared_core_vms/main.tf)  
**Goal:** Verify that shared-core machine types resolve via the Layer-2 static overrides and that billing quantities are correct.

### LLM prompt
> Estimate the cost of `scenarios/scenario_9_shared_core_vms/` and show the billing vCPU count for each instance.

### Expected results
| Instance | Machine type | Billing vCPUs | RAM | Disk |
|---|---|---|---|---|
| `shared_micro` | `e2-micro` | **2** | **1.0 GB** | 10 GB standard |
| `shared_small` | `e2-small` | **2** | **2.0 GB** | 10 GB standard |
| `shared_medium` | `e2-medium` | **2** | **4.0 GB** | 30 GB standard |

- **Check:** billing vCPU qty must be 2 for all three (shared-core billing quirk), not the physical share count

---

## Scenario 10 — Realistic Web-App Stack

**Path:** `scenarios/scenario_10_webapp_stack/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_10_webapp_stack/main.tf)  
**Goal:** Price a multi-tier production architecture: 10 web servers + 1 primary DB + 2 read replicas.

### LLM prompt
> Estimate the total monthly cost of `scenarios/scenario_10_webapp_stack/` and show a cost breakdown by tier.

### Expected results
| Tier | Config | Qty |
|---|---|---|
| Web | `e2-standard-2` + 50 GB `pd-standard` | 10 |
| DB primary | `n2-highmem-8` + 500 GB `pd-ssd` | 1 |
| DB replicas | `n2-highmem-8` + 500 GB `pd-ssd` | 2 |

- **N2 highmem-8:** 8 vCPUs × 8.0 GB/vCPU = **64 GB RAM**
- **Check:** the estimate must produce **13 separate resource entries** (or 3 definition groups with quantities) and the DB replicas must multiply disk cost by 2
- **Total:** should be several hundred dollars/month; LLM must break it down by tier

---

## Scenario 11 — ML Workload (N1 Highmem Trainer + N1 Standard Inference)

**Path:** `scenarios/scenario_11_ml_workload/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_11_ml_workload/main.tf)  
**Goal:** Validate the N1-specific per-family highmem ratio override (6.5 GB/vCPU, not 8.0 GB).

### LLM prompt
> Estimate the cost of `scenarios/scenario_11_ml_workload/` and confirm the RAM allocated to the training node.

### Expected results
- **`ml_trainer`:** `n1-highmem-64` → 64 vCPUs, **416 GB RAM** (64 × 6.5 GB — N1-specific ratio), 1 TB `pd-ssd`
- **`ml_inference` × 4:** `n1-standard-8` → 8 vCPUs, **30 GB RAM** (8 × 3.75 GB — N1-specific ratio), 200 GB `pd-ssd` each
- **Check:** if the LLM reports 512 GB for the training node (8.0 × 64), the N1 override is broken — this is the key assertion

---

## Scenario 12 — What-If Upgrade Baseline

**Path:** `scenarios/scenario_12_what_if_upgrade/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_12_what_if_upgrade/main.tf)  
**Goal:** Provide a baseline for `what_if` and `suggest_cheaper_machine_types` exercises.

### LLM prompt A — What-if machine type change
> What would the cost of `scenarios/scenario_12_what_if_upgrade/` be if I changed the `n2s4-us` instance from `n2-standard-4` to `n2-standard-8`? Show the monthly cost difference.

### Expected results A
- Old cost: on-demand price for `n2-standard-4` (4 vCPUs, 16 GB)
- New cost: on-demand price for `n2-standard-8` (8 vCPUs, 32 GB) — approximately double
- LLM calls `what_if` with `machine_type: n2-standard-8`

### LLM prompt B — Suggest cheaper alternatives
> Suggest cheaper machine types for the `n2s4-us` instance in `scenarios/scenario_12_what_if_upgrade/main.tf`.

### Expected results B
- LLM calls `suggest_cheaper_machine_types`
- Must suggest at least one E2 family alternative (e.g. `e2-standard-4`, `e2-standard-8`) that matches the ≥ 4 vCPU + ≥ 16 GB RAM criteria at a lower price
- Response must include estimated monthly savings per alternative

---

## Scenario 13 — Highcpu Batch Fleet (20 nodes)

**Path:** `scenarios/scenario_13_highcpu_batch_fleet/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_13_highcpu_batch_fleet/main.tf)  
**Goal:** Verify the `highcpu` subtype ratio (1.0 GB RAM per vCPU) and correct multiplication for a large `count`.

### LLM prompt
> Estimate the total monthly cost of the batch fleet in `scenarios/scenario_13_highcpu_batch_fleet/` and confirm the RAM per node.

### Expected results
- **Machine type:** `e2-highcpu-8` → 8 vCPUs, **8.0 GB RAM** (highcpu ratio: 1.0 GB/vCPU × 8)
- **Fleet:** 20 nodes
- **Totals:** qty = 20 × 8 = **160 vCPUs**, 20 × 8 = **160 GB RAM**, 20 × 20 GB = **400 GB** `pd-standard`
- **Check:** RAM per node must be 8 GB, not 32 GB (standard ratio); if 32 GB appears, the highcpu override is broken

---

## Scenario 14 — Partial Failure (Unknown Machine Type)

**Path:** `scenarios/scenario_14_partial_failure/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_14_partial_failure/main.tf)  
**Goal:** Verify the **fail-loud** guarantee: an unknown machine type must appear in `unpriced[]` with a clear reason, while the other VM's cost is still computed and reported.

### LLM prompt
> Estimate the cost of `scenarios/scenario_14_partial_failure/`. Report any resources that could not be priced.

### Expected results
- **Priced:** `app` instance (`n2-standard-4`, `us-central1`, 50 GB `pd-ssd`) — full cost computed
- **Unpriced:** `mystery_vm` (`quantum-turbo-9000`) — must appear in unpriced[] with a reason containing the machine type name or the word "unknown"
- **Check:** the response must NOT silently omit `mystery_vm`; the total cost must only reflect `app`; unpriced items must be called out prominently

---

## Scenario 15 — GKE Cluster & Node Pool

**Path:** `scenarios/scenario_15_gke_cluster/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_15_gke_cluster/main.tf)  
**Goal:** Verify pricing of GKE Clusters with management fees and node pools decomposed into GCE instances and boot disks.

### LLM prompt
> Estimate the infrastructure cost of `scenarios/scenario_15_gke_cluster/` and detail the worker node and cluster management components.

### Expected results
- **Cluster:** `maritime-gke-cluster` → management fee ($0.10/hour, ~$73/month)
- **Worker pool:** `my-node-pool` → quantity 3 nodes of type `e2-standard-4` ($0.134351/vCPU·hr, $0.018005/GB·hr) and 100 GB standard boot disks ($0.0400/GB·month)
- **Output:** separate line items for GKE management fee, node compute, and node boot disks.

---

## Scenario 16 — BigQuery Dataset and Tables

**Path:** `scenarios/scenario_16_bigquery_dataset/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_16_bigquery_dataset/main.tf)  
**Goal:** Verify parsing of BigQuery datasets and handling/warnings for tables.

### LLM prompt
> Parse and estimate the cost for the BigQuery resources in `scenarios/scenario_16_bigquery_dataset/`.

### Expected results
- **Dataset:** `analytics_dataset` → parsed as `bigquery_dataset` with location `US`
- **Tables:** `events_table` → parsed for context but does not emit a separate resource; dataset is the unit of billing.
- **Representative defaults applied:** 100 GB active storage, 1 TB monthly query scan.

---

## Scenario 17 — Combined Tier 1 Stack

**Path:** `scenarios/scenario_17_combined_tier1/`  
**File:** [main.tf](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_17_combined_tier1/main.tf)  
**Goal:** Run a complete integration test of the MCP server across all 5 Tier 1 services.

### LLM prompt
> Parse and estimate the total monthly cost for the combined stack in `scenarios/scenario_17_combined_tier1/`. Break down the costs by service.

### Expected results
- Estimate includes:
  1. **Compute Engine VM:** `app_server` (`e2-medium`, 50 GB standard disk)
  2. **Cloud Storage Bucket:** `static_assets` (`STANDARD` storage class, 100 GB defaults)
  3. **GKE Cluster & Node Pool:** `prod_cluster` & `app_nodes` (management fee + 3 `e2-standard-4` nodes + boot disks)
  4. **Cloud SQL Database:** `prod_db` (PostgreSQL 15, `db-custom-2-7680`, regional HA, 100 GB SSD, backup storage)
  5. **BigQuery Dataset:** `raw_logs` (active storage, query scan, defaults)
- **Output:** total monthly cost encompassing all 5 services with no unpriced items.

---

## Scenario 18 — Natural Language Description

**Path:** `scenarios/scenario_18_nl_description/`  
**File:** [README.md](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/scenarios/scenario_18_nl_description/README.md)  
**Goal:** Test natural language infrastructure parsing, defaults application, validation, and cost calculation.

### LLM prompt
> Estimate the cost for the natural language described stack in `scenarios/scenario_18_nl_description/README.md`.

### Expected results
- The LLM parses the English text and constructs a correct `ResourceModel` JSON payload.
- Model is validated via `validate_resource_model`.
- Total cost is calculated via `estimate_infrastructure` for the 5 services specified in the description.

---

## Advanced Tool Verification Prompts

These prompts work on top of the scenarios above and exercise specific MCP tools directly:

### Cost Optimisation (`suggest_cheaper_machine_types`)
> Recommend ways to reduce the cost of the resources in `scenarios/scenario_1_single_vm/main.tf`.

*Expected:* The LLM calls `suggest_cheaper_machine_types` and suggests migrating from `n2-standard-4` to a cheaper option (e.g. `e2-standard-4`) with an estimated monthly saving.

---

### Regional Cost Comparison (`compare_regions`)
> Compare the cost of `scenarios/scenario_1_single_vm/main.tf` if deployed to `us-central1`, `europe-west1`, `europe-west4`, `asia-east1`, and `us-east1`.

*Expected:* The LLM calls `compare_regions`; returns a ranked table; identifies the cheapest region.

---

### What-If Modification (`what_if`)
> What if we change the machine type in `scenarios/scenario_1_single_vm/main.tf` to `e2-standard-8` and add a second instance?

*Expected:* The LLM calls `what_if`; reports the old vs new monthly cost; shows the cost delta.

---

### Stale Cache Awareness (`get_cache_status`)
> Is the GCP pricing data up to date? When was the cache last refreshed?

*Expected:* The LLM calls `get_cache_status`; reports `last_refreshed_at`, `age_hours`, and `stale` flag; advises refresh if stale.

---

### Cache Refresh (`refresh_pricing_cache`)
> Refresh the GCP pricing cache now.

*Expected:* The LLM calls `refresh_pricing_cache`; confirms success and reports the new snapshot timestamp.

---

### Validate Resource Model (`validate_resource_model`)
> Validate whether this resource model is structurally correct:
> ```json
> {"resources": [{"provider": "gcp", "resource_id": "vm-1", "service": "compute", "kind": "gce_instance", "region": "us-central1", "attributes": {"machine_type": "n2-standard-4"}}]}
> ```

*Expected:* The LLM calls `validate_resource_model`; returns `valid: true` and the validated model.

---

### Find Unpriced Resources (`find_unpriced`)
> Scan `scenarios/scenario_3_unpriced_resources/` and list every resource that cannot be priced.

*Expected:* The LLM calls `find_unpriced` after parsing; returns the storage bucket and pubsub topic in the unpriced list.

---

### Multi-Region + What-If Combined
> Estimate `scenarios/scenario_10_webapp_stack/`. Then tell me: (1) what would it cost if we moved to `europe-west1`? (2) could we save money by switching the web tier from `e2-standard-2` to `e2-highcpu-4`?

*Expected:* The LLM performs a `compare_regions` for region change and a `what_if` for machine type change; compares both results in a single response.
