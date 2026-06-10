resource "google_memorystore_instance" "valkey_standalone" {
  instance_id   = "valkey-standalone"
  location      = "us-central1"
  shard_count   = 1
  node_type     = "SHARED_CORE_NANO"
  mode          = "STANDALONE"
}

resource "google_memorystore_instance" "valkey_cluster" {
  instance_id   = "valkey-cluster"
  location      = "us-central1"
  shard_count   = 3
  node_type     = "STANDARD_SMALL"
  mode          = "CLUSTER"
}
