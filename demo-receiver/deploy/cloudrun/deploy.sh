#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEFAULT_ENV_FILE="${ROOT_DIR}/demo-receiver/deploy/cloudrun/env.local"
ENV_FILE="${DEPLOY_ENV_FILE:-${DEFAULT_ENV_FILE}}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${PROJECT_ID:-}" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "${REGION:-}" ]]; then
  REGION="$(gcloud config get-value run/region 2>/dev/null || true)"
fi

: "${PROJECT_ID:?PROJECT_ID is required (set in env.local, shell env, or gcloud config)}"
: "${REGION:=europe-west1}"
: "${SERVICE_NAME:=nexo-demo-receiver}"

cd "${ROOT_DIR}/demo-receiver"

if [[ ! -f requirements.txt ]]; then
  echo "requirements.txt not found"
  exit 1
fi

# Build using Cloud Buildpacks from source.
gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source . \
  --allow-unauthenticated \
  --set-env-vars "EVENT_TTL_SECONDS=${EVENT_TTL_SECONDS:-86400},MAX_EVENTS_PER_KEY=${MAX_EVENTS_PER_KEY:-200}" \
  --quiet

echo "Deployed ${SERVICE_NAME} in ${PROJECT_ID}/${REGION}"
