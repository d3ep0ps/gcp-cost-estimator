resource "google_compute_instance" "db_backup_server" {
  name         = "backup-server"
  machine_type = "e2-medium"
  zone         = "us-central1-b"

  boot_disk {
    initialize_params {
      size = 30
      type = "pd-standard"
    }
  }
}

resource "google_storage_bucket" "backup_bucket" {
  name     = "my-billing-test-backups-12345"
  location = "US"
}

resource "google_pubsub_topic" "notification_topic" {
  name = "backup-notifications"
}
