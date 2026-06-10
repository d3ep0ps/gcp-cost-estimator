resource "google_spanner_instance" "spanner_pu" {
  name             = "spanner-pu"
  config           = "regional-us-central1"
  processing_units = 100
  edition          = "STANDARD"
}

resource "google_spanner_instance" "spanner_nodes" {
  name      = "spanner-nodes"
  config    = "nam6"
  num_nodes = 2
  edition   = "ENTERPRISE_PLUS"
}

resource "google_spanner_instance" "spanner_unresolved" {
  name             = "spanner-unresolved"
  config           = "regional-us-central1"
  processing_units = var.spanner_pu_var
}
