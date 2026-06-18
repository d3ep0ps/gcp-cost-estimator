resource "google_vertex_ai_endpoint" "dedicated" {
  display_name               = "my-endpoint"
  location                   = "us-central1"
  dedicated_endpoint_enabled = true
}

resource "google_vertex_ai_endpoint" "shared" {
  display_name = "shared-endpoint"
  location     = "us-central1"
  # dedicated_endpoint_enabled defaults to false
}
