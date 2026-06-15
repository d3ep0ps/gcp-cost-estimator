# GCP Services Coverage Target

**Goal:** Implement pricing support for services representing ~90% of typical GCP spend.
**Source:** [Google Cloud pricing list](https://cloud.google.com/pricing/list) (verified June 2026).
**Method:** Services are tiered by typical share of cloud spend across general workloads. Every service implementation must verify its billing model against the official pricing page before committing any fixtures — no prices or SKU IDs from memory.

---

## How to read this list

- **Status:** `done` = already implemented; `in-progress` = active plan exists; `planned` = queued; `deferred` = out of scope for 90% target; `n/a` = no per-usage charge.
- **Pricing page:** the authoritative source to consult before implementation.
- **Terraform resource(s):** the Terraform resource type(s) the IaC parser must handle.
- Services are ordered within each tier by estimated share of spend.

---

## Tier 1 — Core infrastructure (~60% of typical spend)

These five services dominate the bill for the vast majority of GCP customers.

| Service | Status | Pricing page | Terraform resource(s) |
|---|---|---|---|
| Compute Engine (VMs, disks, egress) | done | [compute/all-pricing](https://cloud.google.com/compute/all-pricing) | `google_compute_instance`, `google_compute_disk` |
| Cloud Storage | done | [storage/pricing](https://cloud.google.com/storage/pricing) | `google_storage_bucket` |
| Google Kubernetes Engine | done | [kubernetes-engine/pricing](https://cloud.google.com/kubernetes-engine/pricing) | `google_container_cluster`, `google_container_node_pool` |
| Cloud SQL | done | [sql/pricing](https://cloud.google.com/sql/pricing) | `google_sql_database_instance` |
| BigQuery | done | [bigquery/pricing](https://cloud.google.com/bigquery/pricing) | `google_bigquery_dataset`, `google_bigquery_table` |

---

## Tier 2 — Serverless & containers (~15% of typical spend)

| Service | Status | Pricing page | Terraform resource(s) |
|---|---|---|---|
| Cloud Run | done | [run/pricing](https://cloud.google.com/run/pricing) | `google_cloud_run_v2_service`, `google_cloud_run_v2_job` |
| Cloud Functions | done | [functions/pricing](https://cloud.google.com/functions/pricing) | `google_cloudfunctions_function`, `google_cloudfunctions2_function` |
| App Engine | done | [appengine/pricing](https://cloud.google.com/appengine/pricing) | `google_app_engine_standard_app_version`, `google_app_engine_flexible_app_version` |

---

## Tier 3 — Databases (~8% of typical spend)

| Service | Status | Pricing page | Terraform resource(s) |
|---|---|---|---|
| Cloud Spanner | done | [spanner/pricing](https://cloud.google.com/spanner/pricing) | `google_spanner_instance` |
| Firestore | done | [firestore/pricing](https://cloud.google.com/firestore/pricing) | `google_firestore_database` |
| Memorystore (Redis / Valkey) | done | [memorystore/pricing](https://cloud.google.com/memorystore/pricing) | `google_redis_instance`, `google_memorystore_instance` |
| Bigtable | done | [bigtable/pricing](https://cloud.google.com/bigtable/pricing) | `google_bigtable_instance` |
| AlloyDB for PostgreSQL | done | [alloydb](https://cloud.google.com/alloydb) | `google_alloydb_cluster`, `google_alloydb_instance` |

---

## Tier 4 — Networking (~5% of typical spend)

| Service | Status | Pricing page | Terraform resource(s) |
|---|---|---|---|
| Cloud Load Balancing | done (partial) | [load-balancing/pricing](https://cloud.google.com/load-balancing/pricing) | `google_compute_forwarding_rule`, `google_compute_global_forwarding_rule` |
| Network egress | done (partial) | [vpc/pricing](https://cloud.google.com/vpc/pricing) | (derived from instances) |
| Cloud CDN | planned | [cdn/pricing](https://cloud.google.com/cdn/pricing) | `google_compute_backend_bucket`, `google_compute_backend_service` |
| Cloud DNS | planned | [dns/pricing](https://cloud.google.com/dns/pricing) | `google_dns_managed_zone`, `google_dns_record_set` |
| Cloud NAT | planned | [nat/pricing](https://cloud.google.com/nat/pricing) | `google_compute_router_nat` |
| VPC (static IPs, VPN, Interconnect) | planned | [vpc/pricing](https://cloud.google.com/vpc/pricing) | `google_compute_address`, `google_compute_vpn_gateway` |
| Cloud Armor | planned | [armor/pricing](https://cloud.google.com/armor/pricing) | `google_compute_security_policy` |

---

## Tier 5 — Data & analytics (~5% of typical spend)

| Service | Status | Pricing page | Terraform resource(s) |
|---|---|---|---|
| Pub/Sub | planned | [pubsub/pricing](https://cloud.google.com/pubsub/pricing) | `google_pubsub_topic`, `google_pubsub_subscription` |
| Dataflow | planned | [dataflow/pricing](https://cloud.google.com/dataflow/pricing) | `google_dataflow_job` |
| Dataproc | planned | [dataproc/pricing](https://cloud.google.com/dataproc/pricing) | `google_dataproc_cluster` |

---

## Tier 6 — Storage & AI (~4% of typical spend)

| Service | Status | Pricing page | Terraform resource(s) |
|---|---|---|---|
| Filestore | planned | [filestore/pricing](https://cloud.google.com/filestore/pricing) | `google_filestore_instance` |
| Persistent Disk (standalone) | done | [compute/all-pricing#disk](https://cloud.google.com/compute/all-pricing#disk) | `google_compute_disk` |
| Vertex AI | planned | [vertex-ai/pricing](https://cloud.google.com/vertex-ai/pricing) | `google_vertex_ai_endpoint`, `google_vertex_ai_featurestore` |
| Artifact Registry | planned | [artifact-registry/pricing](https://cloud.google.com/artifact-registry/pricing) | `google_artifact_registry_repository` |

---

## Deferred (v2 / out of scope for 90% target)

These services have pricing but are below the threshold or require specialist billing models not worth implementing before 90% coverage is reached.

| Service | Reason deferred |
|---|---|
| Cloud Logging | Pricing driven by ingested bytes + retention; complex to model from IaC alone |
| Cloud Monitoring | Custom metrics pricing; low share of spend for most customers |
| Secret Manager | Pricing per secret version + access; low spend |
| Cloud Key Management | Per key version + cryptographic operations; low spend |
| Cloud Build | Per build-minute; not declarable from Terraform state meaningfully |
| Workflows | Per step execution; not statically estimable |
| Cloud Scheduler | Per job; negligible spend |
| IoT Core | Deprecated; no new customers |
| Firebase services | Separate billing ecosystem; low overlap with Terraform/GCP IaC |
| Cloud Healthcare API | Specialist; contact-sales pricing |
| Apigee | Enterprise contract pricing; not list-priced |
| Looker | Enterprise contract pricing; not list-priced |
| VMware Engine | Subscription; contact sales |
| Bare Metal | Contact sales |
| Blockchain Node Engine | Niche; low adoption |

---

## Coverage accounting

| Tier | Estimated spend share | Status |
|---|---|---|
| Tier 1 — Core infrastructure | ~60% | 5/5 done ✅ |
| Tier 2 — Serverless & containers | ~15% | 3/3 done ✅ |
| Tier 3 — Databases | ~8% | 5/5 done ✅ |
| Tier 4 — Networking | ~5% | 2/7 done (partial); 5 planned |
| Tier 5 — Data & analytics | ~5% | 0/3 planned |
| Tier 6 — Storage & AI | ~4% | 1/4 done; 3 planned |
| **Total at plan completion** | **~97%** | — |
| **Total currently done** | **~83%** | Tiers 1–3 complete |

---

## Implementation order (recommended)

Work Tier 1 → Tier 2 → Tier 3 in order. Within each tier, pick the highest-spend service first. Tiers 4–6 can be parallelised once Tiers 1–3 are complete.

**Tiers 1–3 complete. Tier 4 + Tier 5 plan drafted ([`plan5.md`](plan5.md)); implementation order:**
1. Cloud CDN (steps CDN-1–CDN-3)
2. Cloud DNS (step DNS-1)
3. Cloud NAT (steps NAT-1–NAT-3)
4. VPC Static IPs (steps VPC-1–VPC-2)
5. Cloud Armor (steps ARM-1–ARM-3)
6. Pub/Sub (steps PS-1–PS-4)
7. Dataflow (steps DF-1–DF-4)
8. Dataproc (steps DP-1–DP-3)

---

## Documentation verification rule (applies to all services)

Before implementing any service in this list, fetch and read its official pricing page (linked above). Do **not** rely on training data for:
- Pricing unit names (e.g. "vCPU-second" vs. "vCPU-hour")
- Free tier thresholds
- SKU groupings
- Regional price variations
- Edition or tier distinctions

Commit a comment in each fixture file citing the exact URL and the date the price was verified.
