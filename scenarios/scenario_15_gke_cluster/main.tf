provider "google" {
  project = "my-project-id"
  region  = "us-central1"
}

resource "google_container_cluster" "primary" {
  name     = "maritime-gke-cluster"
  location = "us-central1"

  initial_node_count       = 1
  remove_default_node_pool = true
}

resource "google_container_node_pool" "primary_preemptible_nodes" {
  name       = "my-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  node_config {
    preemptible  = true
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
  }
}
