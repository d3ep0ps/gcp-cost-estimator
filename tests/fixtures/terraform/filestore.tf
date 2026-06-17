resource "google_filestore_instance" "nfs" {
  name     = "nfs-share"
  location = "us-central1-a"
  tier     = "BASIC_HDD"

  file_shares {
    capacity_gb = 1024
    name        = "vol1"
  }

  networks {
    network = "default"
    modes   = ["MODE_IPV4"]
  }
}
