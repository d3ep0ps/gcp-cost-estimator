resource "google_compute_instance" "shared_micro" {
  name         = "shared-micro"
  machine_type = "e2-micro"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 10
      type  = "pd-standard"
    }
  }
}

resource "google_compute_instance" "shared_small" {
  name         = "shared-small"
  machine_type = "e2-small"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 10
      type  = "pd-standard"
    }
  }
}

resource "google_compute_instance" "shared_medium" {
  name         = "shared-medium"
  machine_type = "e2-medium"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 30
      type  = "pd-standard"
    }
  }
}
