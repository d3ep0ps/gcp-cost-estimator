from typing import Any

CATALOG_DEFAULTS: dict[str, dict[str, Any]] = {
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
}

CATALOG_COVERAGE: dict[str, Any] = {
    "provider": "gcp",
    "services": {
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
    },
}
