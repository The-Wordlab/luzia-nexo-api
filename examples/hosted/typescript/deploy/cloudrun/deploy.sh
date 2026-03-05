#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
DEFAULT_ENV_FILE="${ROOT_DIR}/examples/hosted/typescript/deploy/cloudrun/env.local"
ENV_FILE="${DEPLOY_ENV_FILE:-${DEFAULT_ENV_FILE}}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${PROJECT_ID:-}" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "${REGION:-}" ]]; then
  REGION="$(gcloud config get-value run/region 2>/dev/null || true)"
fi

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:=europe-west1}"
: "${SERVICE_NAME:=nexo-examples-ts}"
: "${EXAMPLES_SHARED_API_SECRET:?EXAMPLES_SHARED_API_SECRET is required}"

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source "${ROOT_DIR}/examples/hosted/typescript" \
  --clear-base-image \
  --allow-unauthenticated \
  --set-env-vars "EXAMPLES_SHARED_API_SECRET=${EXAMPLES_SHARED_API_SECRET}" \
  --quiet

echo "Deployed ${SERVICE_NAME} in ${PROJECT_ID}/${REGION}"
