# Scenario 18 — Natural Language Infrastructure Description

This scenario contains no Terraform files. Instead, it tests the host LLM's capability to understand a natural language description of an infrastructure stack, generate a compliant `ResourceModel` JSON payload, and call the MCP server tools to estimate it.

## Natural Language Description

> "We are building a new application stack in GCP, hosted in `us-east1`. Here are the specifications:
>
> 1. A Kubernetes cluster (GKE Standard) consisting of 5 nodes of type `e2-standard-4`. Each node should have a 150 GB standard boot disk.
> 2. A Cloud SQL database running PostgreSQL 14. It needs to be high-availability (Regional deployment). It should have 4 vCPUs and 16 GB of RAM, with a 200 GB SSD storage disk. Daily backups must be enabled.
> 3. Two Cloud Storage buckets:
>    - A `STANDARD` storage bucket for user media uploads, storing roughly 500 GB of data. We expect around 50,000 upload operations (Class A) and 500,000 read operations (Class B) per month, with 100 GB of internet egress.
>    - An `ARCHIVE` storage bucket for compliance backups, storing 2 TB of data. Egress and operations will be near-zero, but we need to account for it.
> 4. A BigQuery dataset for analytics. We expect to store 1.2 TB of active data. We query about 5 TB of data monthly. There are no streaming inserts.
> 5. A compute VM for a bastion host, which is an `e2-micro` instance with a 20 GB standard boot disk, running 24/7."

## Test Instructions for the LLM

1. Read the natural language description above.
2. Formulate a JSON payload matching the `ResourceModel` schema.
   - Centralize all services in the `us-east1` region (or the specific region mentioned).
   - For GKE, map the cluster and node pool correctly using the `gke_cluster` resource kind.
   - For Cloud SQL, translate "4 vCPUs and 16 GB RAM" to a custom tier `db-custom-4-15360` (since 16 GB = 16384 MB, but custom tiers on GCP are specified in MB and standard ratios are 3.84 GB per vCPU; 4 * 3840 = 15360 MB = 15 GB RAM or similar, but the database custom VM uses `db-custom-4-16384` or `db-custom-4-15360`).
   - For Cloud Storage, map the two buckets with their respective storage classes and usage fields (`size_gb`, `monthly_class_a_ops`, `monthly_class_b_ops`, etc.).
   - For BigQuery, map the dataset, storage size, and query TB usage.
   - For the bastion host, map the GCE instance and standard boot disk.
3. Validate the constructed model using the `validate_resource_model` tool.
4. Estimate the total monthly cost of the infrastructure using the `estimate_infrastructure` tool.
