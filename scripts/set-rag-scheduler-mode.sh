#!/usr/bin/env bash
#
# Set RAG scheduler mode to worker-only or endpoint-only.
#
# Usage:
#   ./scripts/set-rag-scheduler-mode.sh worker
#   ./scripts/set-rag-scheduler-mode.sh endpoint
#
# Required env:
#   GCP_PROJECT_ID
#
# Optional env:
#   GCP_REGION
#   ENDPOINT_PREFIX (default: nexo-rag)
#   WORKER_PREFIX (default: nexo-rag-worker)

set -euo pipefail

MODE="${1:-}"
REGION="${GCP_REGION:-europe-west1}"
ENDPOINT_PREFIX="${ENDPOINT_PREFIX:-nexo-rag}"
WORKER_PREFIX="${WORKER_PREFIX:-nexo-rag-worker}"

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required"
  exit 2
fi

if [[ "$MODE" != "worker" && "$MODE" != "endpoint" ]]; then
  echo "Usage: $0 <worker|endpoint>"
  exit 2
fi

endpoint_jobs=(
  "${ENDPOINT_PREFIX}-news-index"
  "${ENDPOINT_PREFIX}-sports-live-index"
  "${ENDPOINT_PREFIX}-travel-index"
  "${ENDPOINT_PREFIX}-football-live-index"
)

worker_jobs=(
  "${WORKER_PREFIX}-news"
  "${WORKER_PREFIX}-sports"
  "${WORKER_PREFIX}-travel"
  "${WORKER_PREFIX}-football"
)

set_job_state() {
  local job="$1"
  local action="$2" # pause|resume
  if ! gcloud scheduler jobs describe "$job" --project "$GCP_PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
    echo "WARN: job not found: $job"
    return
  fi
  if [[ "$action" == "pause" ]]; then
    gcloud scheduler jobs pause "$job" --project "$GCP_PROJECT_ID" --location "$REGION" >/dev/null
    echo "Paused:  $job"
  else
    gcloud scheduler jobs resume "$job" --project "$GCP_PROJECT_ID" --location "$REGION" >/dev/null
    echo "Enabled: $job"
  fi
}

echo "=== Set RAG Scheduler Mode ==="
echo "Project: ${GCP_PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Mode:    ${MODE}"
echo

if [[ "$MODE" == "worker" ]]; then
  for j in "${endpoint_jobs[@]}"; do
    set_job_state "$j" pause
  done
  for j in "${worker_jobs[@]}"; do
    set_job_state "$j" resume
  done
else
  for j in "${worker_jobs[@]}"; do
    set_job_state "$j" pause
  done
  for j in "${endpoint_jobs[@]}"; do
    set_job_state "$j" resume
  done
fi

echo
echo "Current scheduler states:"
gcloud scheduler jobs list \
  --project "$GCP_PROJECT_ID" \
  --location "$REGION" \
  --format='table(name,state,schedule,httpTarget.uri)' | \
  awk -v ep="$ENDPOINT_PREFIX" -v wp="$WORKER_PREFIX" 'NR==1 || index($1, ep)==1 || index($1, wp)==1'
