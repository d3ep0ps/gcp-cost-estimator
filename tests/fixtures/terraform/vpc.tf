resource "google_compute_address" "my_static_ip" {
  name         = "my-static-ip"
  region       = "us-central1"
  address_type = "EXTERNAL"
}
