# SPDX-License-Identifier: Apache-2.0

from typing import Any

CATALOG_COVERAGE: dict[str, Any] = {
    "provider": "gcp",
    "services": {
        "cdn": {
            "kinds": ["cloud_cdn_backend"],
            "notes": "Cache transfer-out (regional tiers), cache fill, and HTTP/HTTPS requests.",
        },
        "compute": {
            "kinds": ["gce_instance"],
            "notes": "vCPU, RAM, standard/custom machine types, attached PD/SSD disks, egress.",
        },
        "sql": {
            "kinds": ["cloud_sql_instance"],
            "editions": ["ENTERPRISE", "ENTERPRISE_PLUS"],
            "db_versions": ["MYSQL_*", "POSTGRES_*", "SQLSERVER_*"],
            "ha": True,
            "storage_types": ["PD_SSD", "PD_HDD"],
            "notes": "Enterprise Plus SQL Server requires Enterprise licence version.",
        },
        "storage": {
            "kinds": ["gcs_bucket"],
            "storage_classes": ["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"],
            "notes": "Data storage, operations (Class A/B), internet egress, and retrieval fees.",
        },
        "container": {
            "kinds": ["gke_cluster", "gke_node_pool"],
            "notes": (
                "Flat cluster management fee ($0.10/hr), "
                "node pool compute (vCPU/RAM), boot disk storage."
            ),
        },
        "bigquery": {
            "kinds": ["bigquery_dataset"],
            "notes": (
                "Data storage (active/long-term), on-demand query scans, legacy streaming inserts."
            ),
        },
        "run": {
            "kinds": ["cloud_run_service", "cloud_run_job"],
            "notes": "CPU/RAM allocation, invocations, execution time, min/max instances.",
        },
        "functions": {
            "kinds": ["cloud_function"],
            "notes": "1st & 2nd gen function instance classes, memory limits, and regional tiers.",
        },
        "appengine": {
            "kinds": ["app_engine_standard_version", "app_engine_flexible_version"],
            "notes": (
                "Standard Frontend/Backend instance-hours, "
                "flexible CPU/RAM, and standard disk/egress."
            ),
        },
        "spanner": {
            "kinds": ["spanner_instance"],
            "notes": (
                "Compute capacity (processing units/nodes), storage, "
                "and regional/multi-regional configurations."
            ),
        },
        "firestore": {
            "kinds": ["firestore_database"],
            "notes": "Document reads, writes, deletes, and multi-region/regional storage.",
        },
        "memorystore": {
            "kinds": ["redis_instance", "memorystore_instance"],
            "notes": (
                "Redis Basic/Standard HA memory size billing, and Valkey Cluster shard capacities."
            ),
        },
        "bigtable": {
            "kinds": ["bigtable_instance"],
            "notes": (
                "Compute nodes per replicated cluster, SSD/HDD storage, "
                "and multi-cluster replication."
            ),
        },
        "alloydb": {
            "kinds": ["alloydb_cluster", "alloydb_instance"],
            "notes": (
                "Primary/read-pool instance compute (vCPU & RAM), "
                "automated storage, and backup billing."
            ),
        },
        "dns": {
            "kinds": ["dns_managed_zone"],
            "notes": "Managed zones (per zone/month) and DNS query volume.",
        },
        "nat": {
            "kinds": ["nat_gateway"],
            "notes": (
                "Gateway hourly uptime (per VM capped at 32+ VMs), "
                "data processed, and NAT IP uptime."
            ),
        },
        "vpc": {
            "kinds": ["compute_address"],
            "notes": (
                "Static external IP addresses (reserved but unused vs in-use on standard/Spot VMs)."
            ),
        },
        "armor": {
            "kinds": ["compute_security_policy"],
            "notes": "Security policies, rules, and requests processed.",
        },
        "pubsub": {
            "kinds": ["pubsub_topic", "pubsub_subscription"],
            "notes": (
                "Message throughput (excluding first 10 GiB free tier) "
                "and retained message storage."
            ),
        },
        "dataflow": {
            "kinds": ["dataflow_job"],
            "notes": (
                "Batch/streaming jobs compute (vCPU & memory), Shuffle "
                "data volume, and Streaming Engine compute units."
            ),
        },
        "dataproc": {
            "kinds": ["dataproc_cluster"],
            "notes": (
                "Dataproc premium management fee on master/worker node "
                "vCPUs (VM compute estimated separately)."
            ),
        },
        "filestore": {
            "kinds": ["google_filestore_instance"],
            "notes": (
                "Provisioned capacity billing (per GiB-hour), standard and "
                "high-scale tiers, basic HDD instance fees."
            ),
        },
        "vertex": {
            "kinds": ["google_vertex_ai_endpoint"],
            "notes": (
                "Dedicated online prediction endpoint node compute hours; "
                "shared endpoints and traffic-dependent inference costs are unpriced."
            ),
        },
        "artifact": {
            "kinds": ["google_artifact_registry_repository"],
            "notes": (
                "Storage billing with 0.5 GB/month free tier, and "
                "cross-region egress data transfer; vulnerability scanning is unpriced."
            ),
        },
    },
}
