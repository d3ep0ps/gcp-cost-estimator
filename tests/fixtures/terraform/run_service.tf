resource "google_cloud_run_v2_service" "example" {
  name     = "my-run-service"
  location = "us-central1"

  template {
    containers {
      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }
    }
    scaling {
      min_instance_count = 2
      max_instance_count = 10
    }
  }
}

resource "google_cloud_run_v2_job" "example" {
  name     = "my-run-job"
  location = "us-central1"

  template {
    template {
      containers {
        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

variable "run_cpu" {
  type = string
}

resource "google_cloud_run_v2_service" "unresolved" {
  name     = "my-unresolved-service"
  location = "us-central1"

  template {
    containers {
      resources {
        limits = {
          cpu    = var.run_cpu
          memory = "1Gi"
        }
      }
    }
  }
}
