resource "google_service_account" "runtime" {
  account_id   = "nexo-examples-runtime"
  display_name = "Demo Receiver Runtime"
}

resource "google_project_iam_member" "runtime_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_service" "firestore" {
  project            = var.project_id
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.firestore]
}

resource "google_cloud_run_v2_service" "demo_receiver" {
  name     = var.service_name
  location = var.region

  template {
    service_account = google_service_account.runtime.email

    containers {
      image = var.image
      ports {
        container_port = 8080
      }
      env {
        name  = "EVENT_TTL_SECONDS"
        value = tostring(var.event_ttl_seconds)
      }
      env {
        name  = "MAX_EVENTS_PER_KEY"
        value = tostring(var.max_events_per_key)
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    timeout = "30s"
  }

  ingress = "INGRESS_TRAFFIC_ALL"
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_public_invoker ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.demo_receiver.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
