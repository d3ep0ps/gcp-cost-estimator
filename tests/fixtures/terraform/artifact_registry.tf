resource "google_artifact_registry_repository" "docker_repo" {
  location      = "us-central1"
  repository_id = "my-docker-repo"
  description   = "Docker repository"
  format        = "DOCKER"
}
