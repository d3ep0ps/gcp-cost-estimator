resource "google_compute_instance" "app" {
  name         = "app"
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

# Intentionally uses an unrecognised machine type to trigger the unpriced path.
resource "google_compute_instance" "mystery_vm" {
  name         = "mystery-vm"
  machine_type = "quantum-turbo-9000"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
      type  = "pd-ssd"
    }
  }
}
