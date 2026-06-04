resource "google_compute_instance" "app_servers" {
  count        = 3
  name         = "billing-app-server-${count.index}"
  machine_type = "e2-standard-2"
  zone         = "europe-west1-b"

  boot_disk {
    initialize_params {
      size = 50
      type = "pd-standard"
    }
  }
}
