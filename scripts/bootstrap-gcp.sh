#!/usr/bin/env bash
set -euo pipefail

_default_project_id() {
  # Use GCP_PROJECT_ID env var, then PROJECT_ID, then gcloud config
  if [[ -n "${GCP_PROJECT_ID:-}" ]]; then
    echo "${GCP_PROJECT_ID}"
  elif [[ -n "${PROJECT_ID:-}" ]]; then
    echo "${PROJECT_ID}"
  else
    gcloud config get-value project 2>/dev/null || true
  fi
}

PROJECT_ID="$(_default_project_id)"
REGION="${GCP_REGION:-${REGION:-europe-west1}}"
ARTIFACT_REPO="${ARTIFACT_REPO:-nexo-examples}"

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}"
    return 1
  fi
}

check_tools() {
  require_cmd gcloud
  require_cmd gsutil
  require_cmd bq
  require_cmd docker
}

print_versions() {
  echo "== Tool versions =="
  gcloud --version | head -n 5
  docker --version
}

check_auth() {
  echo "== Checking gcloud auth =="
  local active_account
  active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"

  if [[ -z "${active_account}" ]]; then
    echo "No active gcloud account."
    echo "Run: gcloud auth login --update-adc"
    exit 1
  fi

  if ! gcloud auth print-access-token >/dev/null 2>&1; then
    echo "gcloud access token is not usable."
    echo "Run: gcloud auth login --update-adc"
    exit 1
  fi

  if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
    echo "Application Default Credentials are not usable."
    echo "Run: gcloud auth application-default login"
    exit 1
  fi

  echo "Active account: ${active_account}"
}

configure_project() {
  echo "== Configuring project defaults =="
  gcloud config set project "${PROJECT_ID}" >/dev/null
  gcloud config set run/region "${REGION}" >/dev/null
  gcloud config set artifacts/location "${REGION}" >/dev/null
}

configure_adc_quota_project() {
  echo "== Configuring ADC quota project =="
  gcloud auth application-default set-quota-project "${PROJECT_ID}" >/dev/null
}

verify_project() {
  echo "== Verifying target project =="
  local project_number
  project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
  if [[ -z "${project_number}" ]]; then
    echo "Could not retrieve project number for ${PROJECT_ID}"
    exit 1
  fi
  echo "Project verified: ${PROJECT_ID} (${project_number})"
}

enable_services() {
  echo "== Enabling required APIs =="
  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    firestore.googleapis.com \
    iamcredentials.googleapis.com \
    secretmanager.googleapis.com \
    serviceusage.googleapis.com \
    --quiet
}

ensure_artifact_repo() {
  echo "== Ensuring Artifact Registry repo =="
  if ! gcloud artifacts repositories describe "${ARTIFACT_REPO}" \
    --project "${PROJECT_ID}" \
    --location "${REGION}" >/dev/null 2>&1; then
    gcloud artifacts repositories create "${ARTIFACT_REPO}" \
      --project "${PROJECT_ID}" \
      --location "${REGION}" \
      --repository-format docker \
      --description "Partner demo images for nexo-examples" \
      --quiet
  fi
}

print_next_steps() {
  cat <<EOF
== Bootstrap complete ==
Project: ${PROJECT_ID}
Region:  ${REGION}

Next steps:
1. Deploy the demo receiver via Cloud Build:
   GCP_PROJECT_ID=${PROJECT_ID} GCP_REGION=${REGION} make deploy-demo-receiver

2. Deploy hosted example services:
   GCP_PROJECT_ID=${PROJECT_ID} GCP_REGION=${REGION} make deploy-examples
EOF
}

main() {
  if [[ -z "${PROJECT_ID}" ]]; then
    echo "ERROR: No project ID found."
    echo "Set GCP_PROJECT_ID or run: gcloud config set project <your-project-id>"
    exit 1
  fi

  check_tools
  print_versions
  check_auth
  configure_project
  configure_adc_quota_project
  verify_project
  enable_services
  ensure_artifact_repo
  print_next_steps
}

main "$@"
