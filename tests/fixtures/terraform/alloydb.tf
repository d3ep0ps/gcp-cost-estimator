resource "google_alloydb_cluster" "alloydb_cluster" {
  cluster_id = "alloydb-cluster"
  location   = "us-central1"

  initial_user {
    password = "super-secret-password"
  }
}

resource "google_alloydb_instance" "alloydb_primary" {
  cluster       = google_alloydb_cluster.alloydb_cluster.name
  instance_id   = "alloydb-primary"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 4
  }
}

resource "google_alloydb_instance" "alloydb_read_pool" {
  cluster       = google_alloydb_cluster.alloydb_cluster.name
  instance_id   = "alloydb-read-pool"
  instance_type = "READ_POOL"

  read_pool_config {
    node_count = 2
  }

  machine_config {
    cpu_count = 8
  }
}
