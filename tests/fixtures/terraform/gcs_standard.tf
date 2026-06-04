resource "google_storage_bucket" "standard" {
  name          = "my-standard-bucket"
  location      = "US"
  storage_class = "STANDARD"
}

resource "google_storage_bucket" "nearline" {
  name          = "my-nearline-bucket"
  location      = "us-central1"
  storage_class = "NEARLINE"
}

resource "google_storage_bucket" "archive" {
  name          = "my-archive-bucket"
  location      = "europe-west1"
  storage_class = "ARCHIVE"
}

resource "google_storage_bucket" "default_class" {
  name          = "my-default-class-bucket"
  location      = "asia-east1"
}

variable "bucket_location" {
  type = string
}

resource "google_storage_bucket" "unresolved" {
  name     = "my-unresolved-bucket"
  location = var.bucket_location
}
