resource "google_compute_instance" "ml_trainer" {
  name         = "ml-trainer"
  machine_type = "n1-highmem-64"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 1000
      type  = "pd-ssd"
    }
  }
}

resource "google_compute_instance" "ml_inference" {
  count        = 4
  name         = "ml-inference-${count.index}"
  machine_type = "n1-standard-8"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 200
      type  = "pd-ssd"
    }
  }
}
