variable "project_id" {
  type        = string
  description = "GCP project id for demo receiver isolation"
}

variable "region" {
  type        = string
  description = "GCP region"
  default     = "europe-west1"
}

variable "service_name" {
  type        = string
  description = "Cloud Run service name"
  default     = "nexo-demo-receiver"
}

variable "image" {
  type        = string
  description = "Container image URI for demo receiver"
  default     = "gcr.io/cloudrun/hello"
}

variable "allow_public_invoker" {
  type        = bool
  description = "Whether to allow unauthenticated invocations"
  default     = true
}

variable "event_ttl_seconds" {
  type        = number
  default     = 86400
}

variable "max_events_per_key" {
  type        = number
  default     = 200
}
