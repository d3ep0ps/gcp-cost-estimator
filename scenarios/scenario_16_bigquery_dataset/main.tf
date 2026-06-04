provider "google" {
  project = "my-project-id"
  region  = "us-central1"
}

resource "google_bigquery_dataset" "analytics" {
  dataset_id                  = "analytics_dataset"
  friendly_name               = "Analytics Dataset"
  description                 = "Dataset for storing analytics events"
  location                    = "US"
  default_table_expiration_ms = 3600000

  labels = {
    env = "production"
  }
}

resource "google_bigquery_table" "events" {
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "events_table"

  time_partitioning {
    type = "DAY"
  }

  schema = <<EOF
[
  {
    "name": "event_id",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "event_time",
    "type": "TIMESTAMP",
    "mode": "REQUIRED"
  }
]
EOF
}
