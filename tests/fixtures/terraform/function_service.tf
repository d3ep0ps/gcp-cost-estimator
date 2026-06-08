resource "google_cloudfunctions_function" "example" {
  name                = "my-function-1st"
  region              = "us-central1"
  available_memory_mb = 256
}

resource "google_cloudfunctions2_function" "example" {
  name     = "my-function-2nd"
  location = "us-central1"

  service_config {
    available_memory   = "512Mi"
    available_cpu      = "1"
    min_instance_count = 1
  }
}

variable "fn_memory" {
  type = string
}

resource "google_cloudfunctions_function" "unresolved" {
  name                = "my-unresolved-fn"
  region              = "us-central1"
  available_memory_mb = var.fn_memory
}
