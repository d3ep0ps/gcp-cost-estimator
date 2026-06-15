resource "google_pubsub_topic" "my_topic" {
  name = "my-topic"
}

resource "google_pubsub_subscription" "my_sub" {
  name  = "my-sub"
  topic = google_pubsub_topic.my_topic.name

  retain_acked_messages      = true
  message_retention_duration = "86400s"
}
