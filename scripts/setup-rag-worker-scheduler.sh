#!/usr/bin/env bash
#
# Create or update Cloud Scheduler jobs that trigger Cloud Run Jobs workers.
#
# Usage:
#   ./scripts/setup-rag-worker-scheduler.sh <all|news|sports|travel|football>
#
# Required env:
#   GCP_PROJECT_ID
#   SCHEDULER_RUNNER_SA   Service account email used by Scheduler to call Run Jobs API
#
# Optional env:
#   GCP_REGION            Region for Cloud Run Jobs + Scheduler location (default: europe-west1)
#   JOB_PREFIX            Cloud Run Job prefix (default: nexo-rag)
#   SCHEDULER_PREFIX      Scheduler job prefix (default: nexo-rag-worker)

set -euo pipefail

REGION="${GCP_REGION:-europe-west1}"
JOB_PREFIX="${JOB_PREFIX:-nexo-rag}"
SCHEDULER_PREFIX="${SCHEDULER_PREFIX:-nexo-rag-worker}"
ALL_TARGETS="news sports travel football"

usage() {
  echo "Usage: $0 <all|news|sports|travel|football>"
  echo ""
  echo "Required env: GCP_PROJECT_ID, SCHEDULER_RUNNER_SA"
  echo "Optional env: GCP_REGION, JOB_PREFIX, SCHEDULER_PREFIX"
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

if [[ -z "${GCP_PROJECT_ID:-}" || -z "${SCHEDULER_RUNNER_SA:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID and SCHEDULER_RUNNER_SA are required"
  usage
fi

TARGET="$1"
case "$TARGET" in
  all) targets="$ALL_TARGETS" ;;
  news|sports|travel|football) targets="$TARGET" ;;
  *) usage ;;
esac

worker_job_name() {
  echo "${JOB_PREFIX}-$1-worker"
}

scheduler_job_name() {
  echo "${SCHEDULER_PREFIX}-$1"
}

schedule_spec() {
  case "$1" in
    news) echo "*/30 * * * *" ;;
    sports) echo "*/5 * * * *" ;;
    travel) echo "0 * * * *" ;;
    football) echo "*/5 * * * *" ;;
  esac
}

create_or_update_scheduler() {
  local target="$1"
  local worker_job
  worker_job="$(worker_job_name "$target")"
  local scheduler_job
  scheduler_job="$(scheduler_job_name "$target")"
  local schedule
  schedule="$(schedule_spec "$target")"

  local uri="https://run.googleapis.com/v2/projects/${GCP_PROJECT_ID}/locations/${REGION}/jobs/${worker_job}:run"

  echo "Configuring ${scheduler_job}"
  echo "  Schedule: ${schedule}"
  echo "  Trigger:  ${worker_job}"

  if gcloud scheduler jobs describe "$scheduler_job" --project "$GCP_PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$scheduler_job" \
      --project "$GCP_PROJECT_ID" \
      --location "$REGION" \
      --schedule "$schedule" \
      --time-zone "UTC" \
      --uri "$uri" \
      --http-method POST \
      --headers "Content-Type=application/json" \
      --message-body '{}' \
      --oauth-service-account-email "$SCHEDULER_RUNNER_SA" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
  else
    gcloud scheduler jobs create http "$scheduler_job" \
      --project "$GCP_PROJECT_ID" \
      --location "$REGION" \
      --schedule "$schedule" \
      --time-zone "UTC" \
      --uri "$uri" \
      --http-method POST \
      --headers "Content-Type=application/json" \
      --message-body '{}' \
      --oauth-service-account-email "$SCHEDULER_RUNNER_SA" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
  fi
}

echo "=== Configure RAG Worker Scheduler ==="
echo "Project:  ${GCP_PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Targets:  ${targets}"
echo "Runner SA:${SCHEDULER_RUNNER_SA}"
echo ""

for t in $targets; do
  create_or_update_scheduler "$t"
done

echo ""
echo "Done. Current worker scheduler jobs in ${REGION}:"
gcloud scheduler jobs list --project "$GCP_PROJECT_ID" --location "$REGION" \
  --filter="name~${SCHEDULER_PREFIX}" \
  --format='table(name,schedule,httpTarget.uri,state)'
