resource "google_bigtable_instance" "bigtable_ssd" {
  name          = "bigtable-ssd"
  instance_type = "PRODUCTION"

  cluster {
    cluster_id   = "cluster-1"
    zone         = "us-central1-a"
    num_nodes    = 3
    storage_type = "SSD"
  }
}

resource "google_bigtable_instance" "bigtable_multi" {
  name          = "bigtable-multi"
  instance_type = "PRODUCTION"

  cluster {
    cluster_id   = "cluster-1"
    zone         = "us-central1-a"
    num_nodes    = 3
    storage_type = "SSD"
  }

  cluster {
    cluster_id   = "cluster-2"
    zone         = "us-central1-b"
    num_nodes    = 4
    storage_type = "SSD"
  }
}

resource "google_bigtable_instance" "bigtable_dev" {
  name          = "bigtable-dev"
  instance_type = "DEVELOPMENT"

  cluster {
    cluster_id   = "cluster-1"
    zone         = "us-central1-a"
    storage_type = "SSD"
  }
}
