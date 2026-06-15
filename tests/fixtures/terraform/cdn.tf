resource "google_compute_backend_bucket" "cdn_bucket" {
  name        = "cdn-bucket"
  bucket_name = "some-bucket"
  enable_cdn  = true
  region      = "us-central1"
  cdn_policy {
    cache_mode = "CACHE_ALL_STATIC"
  }
}

resource "google_compute_backend_service" "cdn_service" {
  name        = "cdn-service"
  enable_cdn  = true
  region      = "us-central1"
  cdn_policy {
    signed_url_cache_max_age_sec = 7200
  }
}

resource "google_compute_backend_bucket" "no_cdn" {
  name        = "no-cdn"
  bucket_name = "some-bucket"
  enable_cdn  = false
  region      = "us-central1"
}
