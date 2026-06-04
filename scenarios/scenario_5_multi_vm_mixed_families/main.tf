resource "google_compute_instance" "api_server" {
  name         = "api-server"
  machine_type = "n1-standard-8"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
      type  = "pd-ssd"
    }
  }
}

resource "google_compute_instance" "worker" {
  name         = "worker"
  machine_type = "e2-standard-4"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 200
      type  = "pd-standard"
    }
  }
}

resource "google_compute_instance" "cache" {
  name         = "cache"
  machine_type = "n2-highmem-4"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 100
      type  = "pd-ssd"
    }
  }
}
