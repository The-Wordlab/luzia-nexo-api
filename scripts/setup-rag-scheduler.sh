#!/usr/bin/env bash
#
# Create or update Cloud Scheduler jobs for RAG ingest endpoints.
#
# Usage:
#   ./scripts/setup-rag-scheduler.sh <all|news|sports|travel|football>
#
# Required env:
#   GCP_PROJECT_ID
#
# Optional env:
#   GCP_REGION                 Cloud Run region and Scheduler location (default: us-central1)
#   JOB_PREFIX                 Scheduler job prefix (default: nexo-rag)
#   NEWS_SERVICE_URL           Override service URL
#   SPORTS_SERVICE_URL         Override service URL
#   TRAVEL_SERVICE_URL         Override service URL
#   FOOTBALL_SERVICE_URL       Override service URL
#   SCHEDULER_OIDC_SA          Optional service account email for OIDC-authenticated jobs
#   SCHEDULER_OIDC_AUDIENCE    Optional audience for OIDC token (defaults to endpoint URL)

set -euo pipefail

REGION="${GCP_REGION:-us-central1}"
JOB_PREFIX="${JOB_PREFIX:-nexo-rag}"
ALL_TARGETS="news sports travel football"

usage() {
  echo "Usage: $0 <all|news|sports|travel|football>"
  echo ""
  echo "Required env: GCP_PROJECT_ID"
  echo "Optional env: GCP_REGION, JOB_PREFIX, *_SERVICE_URL, SCHEDULER_OIDC_SA, SCHEDULER_OIDC_AUDIENCE"
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required"
  usage
fi

TARGET="$1"
case "$TARGET" in
  all) targets="$ALL_TARGETS" ;;
  news|sports|travel|football) targets="$TARGET" ;;
  *) usage ;;
esac

service_url() {
  case "$1" in
    news) echo "${NEWS_SERVICE_URL:-https://nexo-news-rag-v3me5awkta-ew.a.run.app}" ;;
    sports) echo "${SPORTS_SERVICE_URL:-https://nexo-sports-rag-v3me5awkta-ew.a.run.app}" ;;
    travel) echo "${TRAVEL_SERVICE_URL:-https://nexo-travel-rag-v3me5awkta-ew.a.run.app}" ;;
    football) echo "${FOOTBALL_SERVICE_URL:-https://nexo-football-live-v3me5awkta-ew.a.run.app}" ;;
  esac
}

schedule_spec() {
  case "$1" in
    news) echo "*/30 * * * *" ;;
    sports) echo "*/5 * * * *" ;;
    travel) echo "0 * * * *" ;;
    football) echo "*/5 * * * *" ;;
  esac
}

endpoint_path() {
  case "$1" in
    news) echo "/ingest" ;;
    sports) echo "/ingest/live" ;;
    travel) echo "/ingest" ;;
    football) echo "/ingest/live" ;;
  esac
}

job_name() {
  case "$1" in
    news) echo "${JOB_PREFIX}-news-index" ;;
    sports) echo "${JOB_PREFIX}-sports-live-index" ;;
    travel) echo "${JOB_PREFIX}-travel-index" ;;
    football) echo "${JOB_PREFIX}-football-live-index" ;;
  esac
}

create_or_update_job() {
  local target="$1"
  local name
  name="$(job_name "$target")"
  local base
  base="$(service_url "$target")"
  local path
  path="$(endpoint_path "$target")"
  local schedule
  schedule="$(schedule_spec "$target")"
  local uri="${base}${path}"

  echo "Configuring ${name}"
  echo "  URL: ${uri}"
  echo "  Schedule: ${schedule}"

  local -a auth_flags
  auth_flags=()
  if [[ -n "${SCHEDULER_OIDC_SA:-}" ]]; then
    auth_flags+=("--oidc-service-account-email=${SCHEDULER_OIDC_SA}")
    auth_flags+=("--oidc-token-audience=${SCHEDULER_OIDC_AUDIENCE:-$uri}")
  fi

  if gcloud scheduler jobs describe "$name" --project "$GCP_PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
    if [[ ${#auth_flags[@]} -gt 0 ]]; then
      gcloud scheduler jobs update http "$name" \
        --project "$GCP_PROJECT_ID" \
        --location "$REGION" \
        --schedule "$schedule" \
        --time-zone "UTC" \
        --uri "$uri" \
        --http-method POST \
        --headers "Content-Type=application/json" \
        --message-body '{}' \
        "${auth_flags[@]}"
    else
      gcloud scheduler jobs update http "$name" \
        --project "$GCP_PROJECT_ID" \
        --location "$REGION" \
        --schedule "$schedule" \
        --time-zone "UTC" \
        --uri "$uri" \
        --http-method POST \
        --headers "Content-Type=application/json" \
        --message-body '{}'
    fi
  else
    if [[ ${#auth_flags[@]} -gt 0 ]]; then
      gcloud scheduler jobs create http "$name" \
        --project "$GCP_PROJECT_ID" \
        --location "$REGION" \
        --schedule "$schedule" \
        --time-zone "UTC" \
        --uri "$uri" \
        --http-method POST \
        --headers "Content-Type=application/json" \
        --message-body '{}' \
        "${auth_flags[@]}"
    else
      gcloud scheduler jobs create http "$name" \
        --project "$GCP_PROJECT_ID" \
        --location "$REGION" \
        --schedule "$schedule" \
        --time-zone "UTC" \
        --uri "$uri" \
        --http-method POST \
        --headers "Content-Type=application/json" \
        --message-body '{}'
    fi
  fi
}

echo "=== Configure RAG Scheduler Jobs ==="
echo "Project: ${GCP_PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Target:  ${targets}"
echo ""

for t in $targets; do
  create_or_update_job "$t"
done

echo ""
echo "Done. Current jobs in ${REGION}:"
gcloud scheduler jobs list --project "$GCP_PROJECT_ID" --location "$REGION" \
  --format='table(name,schedule,httpTarget.uri,state)'
