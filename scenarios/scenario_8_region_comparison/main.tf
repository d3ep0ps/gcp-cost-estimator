resource "google_compute_instance" "eu_vm" {
  name         = "eu-vm"
  machine_type = "n2-standard-4"
  zone         = "europe-west4-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 100
      type  = "pd-ssd"
    }
  }
}
