resource "google_dataproc_cluster" "my_cluster" {
  name   = "my-cluster"
  region = "us-central1"

  master_config {
    num_instances = 1
    machine_type  = "n1-standard-4"
  }

  worker_config {
    num_instances = 2
    machine_type  = "n1-standard-4"
  }

  preemptible_worker_config {
    num_instances = 0
  }
}

resource "google_dataproc_serverless_batch" "my_batch" {
  name          = "my-batch"
  region        = "us-central1"
  runtime_config {
    version = "2.0"
  }
}
