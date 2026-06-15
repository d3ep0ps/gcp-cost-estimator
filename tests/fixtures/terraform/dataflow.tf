resource "google_dataflow_job" "my_job" {
  name              = "my-job"
  template_gcs_path = "gs://my-bucket/template"
  temp_gcs_location = "gs://my-bucket/tmp"
  region            = "us-central1"
  machine_type      = "n1-standard-4"
  max_workers       = 2
}
