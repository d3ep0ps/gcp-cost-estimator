variable "machine_type" {
  type        = string
  description = "The GCE machine type"
}

variable "disk_size" {
  type        = number
  description = "Size of boot disk"
}

resource "google_compute_instance" "web_nodes" {
  count        = var.node_count
  name         = "web-node-${count.index}"
  machine_type = var.machine_type
  zone         = "us-central1-b"

  boot_disk {
    initialize_params {
      size = var.disk_size
      type = "pd-ssd"
    }
  }
}
