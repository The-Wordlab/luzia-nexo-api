output "service_url" {
  value = google_cloud_run_v2_service.demo_receiver.uri
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}
