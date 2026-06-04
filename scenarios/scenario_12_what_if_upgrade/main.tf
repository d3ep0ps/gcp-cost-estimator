resource "google_compute_instance" "n2s4_us" {
  name         = "n2s4-us"
  machine_type = "n2-standard-4"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
      type  = "pd-ssd"
    }
  }
}

resource "google_compute_instance" "e2s8_us" {
  name         = "e2s8-us"
  machine_type = "e2-standard-8"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
      type  = "pd-ssd"
    }
  }
}
