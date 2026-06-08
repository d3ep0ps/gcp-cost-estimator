resource "google_app_engine_application" "app" {
  project     = "my-project"
  location_id = "us-central"
}

resource "google_app_engine_standard_app_version" "example" {
  service        = "default"
  version_id     = "v1"
  runtime        = "python312"
  instance_class = "F2"

  automatic_scaling {
    min_idle_instances = 1
    max_idle_instances = 3
  }
}

resource "google_app_engine_flexible_app_version" "example" {
  service    = "default"
  version_id = "v1"
  runtime    = "python"

  resources {
    cpu       = 1
    memory_gb = 2
    disk_gb   = 10
  }
}

variable "ae_class" {
  type = string
}

resource "google_app_engine_standard_app_version" "unresolved" {
  service        = "default"
  version_id     = "v1"
  runtime        = "python312"
  instance_class = var.ae_class
}

resource "google_app_engine_flexible_app_version" "missing_resources" {
  service    = "default"
  version_id = "v1"
  runtime    = "python"
}
