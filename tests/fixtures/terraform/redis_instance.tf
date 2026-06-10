resource "google_redis_instance" "redis_basic" {
  name           = "redis-basic"
  memory_size_gb = 5
  tier           = "BASIC"
  region         = "us-central1"
}

resource "google_redis_instance" "redis_ha" {
  name           = "redis-ha"
  memory_size_gb = 10
  tier           = "STANDARD_HA"
  region         = "us-central1"
}
