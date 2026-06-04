resource "google_compute_instance" "web" {
  count        = 10
  name         = "web-${count.index}"
  machine_type = "e2-standard-2"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
      type  = "pd-standard"
    }
  }
}

resource "google_compute_instance" "db_primary" {
  name         = "db-primary"
  machine_type = "n2-highmem-8"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 500
      type  = "pd-ssd"
    }
  }
}

resource "google_compute_instance" "db_replica" {
  count        = 2
  name         = "db-replica-${count.index}"
  machine_type = "n2-highmem-8"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 500
      type  = "pd-ssd"
    }
  }
}
