# SPDX-License-Identifier: Apache-2.0

from typing import Any

CATALOG_DEFAULTS: dict[str, dict[str, Any]] = {
    "cdn": {
        "monthly_cache_transfer_gb": {
            "value": 100,
            "unit": "GB/month",
            "hint": "Override usage.monthly_cache_transfer_gb with expected CDN delivery volume.",
        },
        "monthly_cache_fill_gb": {
            "value": 10,
            "unit": "GB/month",
            "hint": "Override usage.monthly_cache_fill_gb with expected origin fill volume.",
        },
        "monthly_requests": {
            "value": 1000000,
            "unit": "requests/month",
            "hint": "Override usage.monthly_requests.",
        },
        "https_fraction": {
            "value": 1.0,
            "unit": "fraction",
            "hint": "Fraction of requests that are HTTPS (0.0–1.0).",
        },
    },
    "compute": {
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 workloads.",
        },
    },
    "storage": {
        "storage_class": {
            "value": "STANDARD",
            "unit": None,
            "hint": "Override attributes.storage_class (NEARLINE/COLDLINE/ARCHIVE for cold data).",
        },
        "size_gb": {
            "value": 100,
            "unit": "GB",
            "hint": "Override usage.size_gb with your expected data volume.",
        },
        "monthly_class_a_ops": {
            "value": 10_000,
            "unit": "ops/month",
            "hint": "Override usage.monthly_class_a_ops (~300 writes/day assumed).",
        },
        "monthly_class_b_ops": {
            "value": 100_000,
            "unit": "ops/month",
            "hint": "Override usage.monthly_class_b_ops (~3,000 reads/day assumed).",
        },
        "monthly_egress_gb": {
            "value": 10,
            "unit": "GB/month",
            "hint": "Override usage.monthly_egress_gb with expected internet egress.",
        },
        "monthly_retrieval_gb": {
            "value": 0,
            "unit": "GB/month",
            "hint": "Set usage.monthly_retrieval_gb for Nearline/Coldline/Archive retrieval.",
        },
    },
    "container": {
        "node_count": {
            "value": 3,
            "unit": "nodes",
            "hint": "Override attributes.node_count with your actual cluster size.",
        },
        "machine_type": {
            "value": "e2-standard-4",
            "unit": None,
            "hint": "Override attributes.machine_type with your node machine type.",
        },
        "disk_size_gb": {
            "value": 100,
            "unit": "GB",
            "hint": "Override attributes.disk_size_gb with your node boot disk size.",
        },
        "disk_type": {
            "value": "pd-standard",
            "unit": None,
            "hint": "Override attributes.disk_type (pd-ssd for better I/O).",
        },
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 clusters.",
        },
    },
    "bigquery": {
        "active_storage_gb": {
            "value": 100,
            "unit": "GB",
            "hint": "Override usage.active_storage_gb with your dataset size.",
        },
        "long_term_storage_gb": {
            "value": 0,
            "unit": "GB",
            "hint": "Set usage.long_term_storage_gb for data unmodified >90 days.",
        },
        "monthly_query_tb": {
            "value": 1,
            "unit": "TB/month",
            "hint": "Override usage.monthly_query_tb with your expected query volume.",
        },
        "monthly_streaming_gb": {
            "value": 0,
            "unit": "GB/month",
            "hint": "Set usage.monthly_streaming_gb if using the legacy Streaming API.",
        },
    },
    "sql": {
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 databases.",
        },
        "disk_type": {
            "value": "PD_SSD",
            "unit": None,
            "hint": "Override attributes.disk_type (PD_HDD not supported for SQL Server).",
        },
        "availability_type": {
            "value": "ZONAL",
            "unit": None,
            "hint": "Set attributes.availability_type=REGIONAL for HA (doubles compute cost).",
        },
        "backup_enabled": {
            "value": False,
            "unit": None,
            "hint": "Set attributes.backup_enabled=true to include backup storage cost.",
        },
    },
    "run": {
        "invocations_per_month": {
            "value": 10_000,
            "unit": "invocations/month",
            "hint": "Override usage.invocations_per_month.",
        },
        "runtime_seconds_per_invocation": {
            "value": 1,
            "unit": "seconds",
            "hint": "Override usage.runtime_seconds_per_invocation.",
        },
    },
    "functions": {
        "invocations_per_month": {
            "value": 1_000_000,
            "unit": "invocations/month",
            "hint": "Override usage.invocations_per_month.",
        },
        "avg_execution_time_ms": {
            "value": 100,
            "unit": "ms",
            "hint": "Override usage.avg_execution_time_ms.",
        },
    },
    "appengine": {
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month.",
        },
    },
    "spanner": {
        "processing_units": {
            "value": 100,
            "unit": "PU",
            "hint": "Override attributes.processing_units. 1 node = 1000 PU.",
        },
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 instances.",
        },
        "storage_gb": {
            "value": 0,
            "unit": "GB",
            "hint": "Override usage.storage_gb with your expected data size.",
        },
        "monthly_egress_gb": {
            "value": 0,
            "unit": "GB/month",
            "hint": "Override usage.monthly_egress_gb with expected internet egress.",
        },
    },
    "firestore": {
        "storage_gb": {
            "value": 1,
            "unit": "GB",
            "hint": "Override usage.storage_gb with your expected document store size.",
        },
        "monthly_reads": {
            "value": 500_000,
            "unit": "reads/month",
            "hint": "Override usage.monthly_reads (~16K reads/day assumed).",
        },
        "monthly_writes": {
            "value": 100_000,
            "unit": "writes/month",
            "hint": "Override usage.monthly_writes (~3K writes/day assumed).",
        },
        "monthly_deletes": {
            "value": 10_000,
            "unit": "deletes/month",
            "hint": "Override usage.monthly_deletes (~330 deletes/day assumed).",
        },
        "monthly_egress_gb": {
            "value": 0,
            "unit": "GB/month",
            "hint": "Override usage.monthly_egress_gb with expected internet egress.",
        },
    },
    "memorystore": {
        "tier": {
            "value": "BASIC",
            "unit": None,
            "hint": "Override attributes.tier to STANDARD_HA for high availability.",
        },
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 caches.",
        },
    },
    "bigtable": {
        "instance_type": {
            "value": "PRODUCTION",
            "unit": None,
            "hint": "Override attributes.instance_type to DEVELOPMENT for non-production use.",
        },
        "num_nodes_per_cluster": {
            "value": 3,
            "unit": "nodes",
            "hint": "Override cluster.num_nodes to match your provisioned cluster size.",
        },
        "storage_type": {
            "value": "SSD",
            "unit": None,
            "hint": (
                "Override cluster.storage_type to HDD for cost reduction "
                "on throughput-tolerant workloads."
            ),
        },
        "storage_gb_per_cluster": {
            "value": 0,
            "unit": "GB",
            "hint": "Override usage.storage_gb_per_cluster with your expected data size.",
        },
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 instances.",
        },
    },
    "alloydb": {
        "storage_gb": {
            "value": 100,
            "unit": "GB",
            "hint": "Override usage.storage_gb with your expected database size.",
        },
        "backup_enabled": {
            "value": False,
            "unit": None,
            "hint": "Set usage.backup_enabled=true to include backup storage cost.",
        },
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for non-24/7 databases.",
        },
        "node_count": {
            "value": 1,
            "unit": "nodes",
            "hint": "Override attributes.node_count (READ_POOL instances only).",
        },
    },
    "dns": {
        "monthly_queries": {
            "value": 1000000,
            "unit": "queries/month",
            "hint": "Override usage.monthly_queries with expected DNS query volume.",
        },
    },
    "nat": {
        "num_vms": {
            "value": 1,
            "unit": "VMs",
            "hint": "Override usage.num_vms with the number of VMs routed through this NAT gateway.",
        },
        "num_nat_ips": {
            "value": 1,
            "unit": "IPs",
            "hint": "Override usage.num_nat_ips with the number of external IPs allocated.",
        },
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override for non-24/7 gateways.",
        },
        "monthly_data_processed_gb": {
            "value": 10,
            "unit": "GB/month",
            "hint": "Override usage.monthly_data_processed_gb with expected throughput.",
        },
    },
    "vpc": {
        "runtime_hours_per_month": {
            "value": 730,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month for the IP reservation duration.",
        },
        "in_use": {
            "value": True,
            "unit": "bool",
            "hint": "Set to false if IP is reserved but not yet attached.",
        },
        "on_spot_vm": {
            "value": False,
            "unit": "bool",
            "hint": "Set to true if IP is attached to a Spot/preemptible VM.",
        },
        "on_forwarding_rule": {
            "value": False,
            "unit": "bool",
            "hint": "Set to true if IP is attached to a forwarding rule or VPN tunnel (no charge).",
        },
    },
    "armor": {
        "monthly_requests": {
            "value": 1000000,
            "unit": "requests/month",
            "hint": "Override usage.monthly_requests with expected request volume to the policy.",
        },
    },
    "pubsub": {
        "monthly_message_throughput_gb": {
            "value": 10.0,
            "unit": "GB/month",
            "hint": "Override usage.monthly_message_throughput_gb with expected total message volume.",
        },
        "subscription_storage_gb": {
            "value": 0.0,
            "unit": "GB",
            "hint": "Override usage.subscription_storage_gb when retain_acked_messages is enabled.",
        },
    },
    "dataflow": {
        "num_vcpus": {
            "value": 4,
            "unit": "vCPUs",
            "hint": "Derived from machine_type if set; override otherwise.",
        },
        "memory_gb": {
            "value": 15.0,
            "unit": "GB",
            "hint": "Derived from machine_type if set; override otherwise.",
        },
        "runtime_hours_per_month": {
            "value": 100,
            "unit": "hours",
            "hint": "Override usage.runtime_hours_per_month with job frequency x duration.",
        },
        "job_type": {
            "value": "batch",
            "unit": "string",
            "hint": "Set to 'streaming' for long-running streaming jobs.",
        },
        "shuffle_data_gb": {
            "value": 50.0,
            "unit": "GB",
            "hint": "Override usage.shuffle_data_gb for batch jobs.",
        },
    },
    "dataproc": {
        "num_master_vcpus": {
            "value": 4,
            "unit": "vCPUs",
            "hint": "n1-standard-4 master",
        },
        "num_worker_vcpus": {
            "value": 8,
            "unit": "vCPUs",
            "hint": "2 x n1-standard-4 workers",
        },
        "runtime_hours_per_month": {
            "value": 100,
            "unit": "hours",
            "hint": "~3 hours/day jobs",
        },
    },
}

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
            "notes": "Gateway hourly uptime (per VM capped at 32+ VMs), data processed, and NAT IP uptime.",
        },
        "vpc": {
            "kinds": ["compute_address"],
            "notes": "Static external IP addresses (reserved but unused vs in-use on standard/Spot VMs).",
        },
        "armor": {
            "kinds": ["compute_security_policy"],
            "notes": "Security policies, rules, and requests processed.",
        },
        "pubsub": {
            "kinds": ["pubsub_topic", "pubsub_subscription"],
            "notes": "Message throughput (excluding first 10 GiB free tier) and retained message storage.",
        },
        "dataflow": {
            "kinds": ["dataflow_job"],
            "notes": "Batch/streaming jobs compute (vCPU & memory), Shuffle data volume, and Streaming Engine compute units.",
        },
        "dataproc": {
            "kinds": ["dataproc_cluster"],
            "notes": "Dataproc premium management fee on master/worker node vCPUs (VM compute estimated separately).",
        },
    },
}
