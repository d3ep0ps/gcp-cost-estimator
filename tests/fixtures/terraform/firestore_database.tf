resource "google_firestore_database" "firestore_native" {
  name        = "fs-native"
  location_id = "us-central"
  type        = "FIRESTORE_NATIVE"
}

resource "google_firestore_database" "firestore_datastore" {
  name        = "fs-datastore"
  location_id = "europe-west"
  type        = "DATASTORE_MODE"
}

resource "google_firestore_database" "firestore_default_type" {
  name        = "fs-default-type"
  location_id = "us-central"
}

resource "google_firestore_database" "firestore_unresolved" {
  name        = "fs-unresolved"
  location_id = var.location_var
}
