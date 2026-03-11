#!/usr/bin/env bash
#
# Validate Cloud Scheduler configuration for RAG indexing jobs.
#
# Modes:
# - endpoint: Scheduler calls /ingest endpoints on Cloud Run services
# - worker:   Scheduler calls Cloud Run Jobs API endpoints
#
# Usage:
#   ./scripts/check-rag-scheduler.sh [endpoint|worker]
#
# Required env:
#   GCP_PROJECT_ID
#
# Optional env:
#   GCP_REGION
#   JOB_PREFIX
#   SCHEDULER_PREFIX
#   WORKER_SCHEDULER_PREFIX

set -euo pipefail

MODE="${1:-endpoint}"
REGION="${GCP_REGION:-europe-west1}"
JOB_PREFIX="${JOB_PREFIX:-nexo-rag}"
SCHEDULER_PREFIX="${SCHEDULER_PREFIX:-nexo-rag}"
WORKER_SCHEDULER_PREFIX="${WORKER_SCHEDULER_PREFIX:-nexo-rag-worker}"

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required"
  exit 2
fi

if [[ "$MODE" != "endpoint" && "$MODE" != "worker" ]]; then
  echo "ERROR: mode must be one of: endpoint, worker"
  exit 2
fi

service_url() {
  local service="$1"
  gcloud run services describe "$service" \
    --project "$GCP_PROJECT_ID" \
    --region "$REGION" \
    --format='value(status.url)'
}

expect_endpoint_uri() {
  case "$1" in
    news) echo "$(service_url nexo-news-rag)/ingest" ;;
    sports) echo "$(service_url nexo-sports-rag)/ingest/live" ;;
    travel) echo "$(service_url nexo-travel-rag)/ingest" ;;
    football) echo "$(service_url nexo-football-live)/ingest/live" ;;
  esac
}

expect_worker_uri() {
  local job_name="${JOB_PREFIX}-$1-worker"
  echo "https://run.googleapis.com/v2/projects/${GCP_PROJECT_ID}/locations/${REGION}/jobs/${job_name}:run"
}

schedule_for() {
  case "$1" in
    news) echo "*/30 * * * *" ;;
    sports) echo "*/5 * * * *" ;;
    travel) echo "0 * * * *" ;;
    football) echo "*/5 * * * *" ;;
  esac
}

scheduler_name() {
  if [[ "$MODE" == "endpoint" ]]; then
    case "$1" in
      news) echo "${SCHEDULER_PREFIX}-news-index" ;;
      sports) echo "${SCHEDULER_PREFIX}-sports-live-index" ;;
      travel) echo "${SCHEDULER_PREFIX}-travel-index" ;;
      football) echo "${SCHEDULER_PREFIX}-football-live-index" ;;
    esac
  else
    echo "${WORKER_SCHEDULER_PREFIX}-$1"
  fi
}

check_one() {
  local target="$1"
  local name
  name="$(scheduler_name "$target")"

  local expected_uri
  if [[ "$MODE" == "endpoint" ]]; then
    expected_uri="$(expect_endpoint_uri "$target")"
  else
    expected_uri="$(expect_worker_uri "$target")"
  fi

  local expected_schedule
  expected_schedule="$(schedule_for "$target")"

  local got_uri got_schedule got_state
  got_uri="$(gcloud scheduler jobs describe "$name" --project "$GCP_PROJECT_ID" --location "$REGION" --format='value(httpTarget.uri)' 2>/dev/null || true)"
  got_schedule="$(gcloud scheduler jobs describe "$name" --project "$GCP_PROJECT_ID" --location "$REGION" --format='value(schedule)' 2>/dev/null || true)"
  got_state="$(gcloud scheduler jobs describe "$name" --project "$GCP_PROJECT_ID" --location "$REGION" --format='value(state)' 2>/dev/null || true)"

  if [[ -z "$got_uri" ]]; then
    echo "[FAIL] ${name}: job not found"
    return 1
  fi

  if [[ "$got_uri" != "$expected_uri" ]]; then
    echo "[FAIL] ${name}: uri mismatch"
    echo "       expected: $expected_uri"
    echo "       got:      $got_uri"
    return 1
  fi

  if [[ "$got_schedule" != "$expected_schedule" ]]; then
    echo "[FAIL] ${name}: schedule mismatch"
    echo "       expected: $expected_schedule"
    echo "       got:      $got_schedule"
    return 1
  fi

  if [[ "$got_state" != "ENABLED" ]]; then
    echo "[FAIL] ${name}: state is $got_state (expected ENABLED)"
    return 1
  fi

  echo "[OK] ${name}"
  return 0
}

echo "=== Check RAG Scheduler (${MODE}) ==="
echo "Project: ${GCP_PROJECT_ID}"
echo "Region:  ${REGION}"

fail=0
for t in news sports travel football; do
  if ! check_one "$t"; then
    fail=1
  fi
done

if [[ $fail -ne 0 ]]; then
  echo "Scheduler check failed"
  exit 1
fi

echo "Scheduler check passed"
