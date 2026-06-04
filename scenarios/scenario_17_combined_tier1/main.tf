provider "google" {
  project = "my-project-id"
  region  = "us-central1"
}

# 1. Compute Engine Instance
resource "google_compute_instance" "app_server" {
  name         = "app-server"
  machine_type = "e2-medium"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      size = 50
      type = "pd-standard"
    }
  }
}

# 2. Cloud Storage Bucket
resource "google_storage_bucket" "static_assets" {
  name          = "my-app-static-assets-12345"
  location      = "US"
  storage_class = "STANDARD"
}

# 3. GKE Cluster & Node Pool
resource "google_container_cluster" "prod_cluster" {
  name     = "prod-gke-cluster"
  location = "us-central1"

  initial_node_count       = 1
  remove_default_node_pool = true
}

resource "google_container_node_pool" "app_nodes" {
  name       = "app-nodes"
  location   = "us-central1"
  cluster    = google_container_cluster.prod_cluster.name
  node_count = 3

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
  }
}

# 4. Cloud SQL Instance
resource "google_sql_database_instance" "prod_db" {
  name             = "prod-db-instance"
  database_version = "POSTGRES_15"
  region           = "us-central1"

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "REGIONAL"
    disk_type         = "PD_SSD"
    disk_size         = 100

    backup_configuration {
      enabled = true
    }
  }
}

# 5. BigQuery Dataset
resource "google_bigquery_dataset" "raw_logs" {
  dataset_id = "raw_logs_dataset"
  location   = "US"
}
