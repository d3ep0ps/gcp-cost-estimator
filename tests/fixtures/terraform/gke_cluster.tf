resource "google_container_cluster" "minimal" {
  name     = "gke-minimal"
  location = "us-central1"
}

resource "google_container_cluster" "with_node_config" {
  name               = "gke-node-config"
  location           = "us-central1"
  initial_node_count = 3

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
  }
}

resource "google_container_node_pool" "pool" {
  name       = "gke-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.with_node_config.name
  node_count = 2

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-ssd"
  }
}

variable "gke_nodes" {
  type = number
}

variable "gke_mtype" {
  type = string
}

resource "google_container_cluster" "unresolved_nodes" {
  name               = "gke-unresolved-nodes"
  location           = "us-central1"
  initial_node_count = var.gke_nodes
}

resource "google_container_cluster" "unresolved_mtype" {
  name     = "gke-unresolved-mtype"
  location = "us-central1"
  node_config {
    machine_type = var.gke_mtype
  }
}
