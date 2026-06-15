resource "google_compute_router_nat" "my_nat" {
  name                               = "my-nat"
  router                             = "my-router"
  region                             = "us-central1"
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
