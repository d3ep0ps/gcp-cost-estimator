resource "google_bigquery_dataset" "minimal" {
  dataset_id = "bq_minimal"
}

resource "google_bigquery_dataset" "with_location" {
  dataset_id = "bq_with_location"
  location   = "US"
}

variable "dataset_location" {
  type = string
}

resource "google_bigquery_dataset" "unresolved" {
  dataset_id = "bq_unresolved"
  location   = var.dataset_location
}

resource "google_bigquery_table" "table_in_dataset" {
  dataset_id = google_bigquery_dataset.with_location.dataset_id
  table_id   = "my_table"
}

resource "google_bigquery_table" "orphan_table" {
  dataset_id = "nonexistent_dataset"
  table_id   = "orphan"
}
