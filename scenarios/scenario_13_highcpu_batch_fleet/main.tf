resource "google_compute_instance" "batch_job" {
  count        = 20
  name         = "batch-${count.index}"
  machine_type = "e2-highcpu-8"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 20
      type  = "pd-standard"
    }
  }
}
