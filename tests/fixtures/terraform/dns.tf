resource "google_dns_managed_zone" "my_zone" {
  name        = "my-zone"
  dns_name    = "example.com."
  description = "Example Zone"
  visibility  = "public"
}
