resource "google_compute_instance" "spot_worker" {
  name         = "spot-worker"
  machine_type = "n2-standard-4"
  zone         = "us-central1-a"

  scheduling {
    preemptible       = true
    automatic_restart = false
  }

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
      type  = "pd-standard"
    }
  }
}
