resource "google_compute_instance" "custom_vm" {
  name         = "custom-vm"
  machine_type = "custom-6-20480"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 100
      type  = "pd-ssd"
    }
  }
}
