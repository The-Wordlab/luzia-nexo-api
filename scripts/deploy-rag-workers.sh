#!/usr/bin/env bash
#
# Create or update Cloud Run Jobs for RAG ingest workers.
#
# Usage:
#   ./scripts/deploy-rag-workers.sh <all|news|sports|travel|football>
#
# Required env:
#   GCP_PROJECT_ID
#
# Optional env:
#   GCP_REGION         Cloud Run region (default: europe-west1)
#   AR_REPO            Artifact Registry repo (default: nexo-examples)
#   JOB_PREFIX         Cloud Run Job name prefix (default: nexo-rag)
#   JOB_TASK_TIMEOUT   Timeout for one worker run (default: 900s)
#   JOB_MAX_RETRIES    Retries per run (default: 1)
#
# Worker defaults:
# - news:     python ingest.py
# - sports:   python worker.py with SPORTS_WORKER_MODE=live
# - travel:   python worker.py
# - football: python worker.py with FOOTBALL_WORKER_MODE=live

set -euo pipefail

REGION="${GCP_REGION:-europe-west1}"
AR_REPO="${AR_REPO:-nexo-examples}"
JOB_PREFIX="${JOB_PREFIX:-nexo-rag}"
JOB_TASK_TIMEOUT="${JOB_TASK_TIMEOUT:-900s}"
JOB_MAX_RETRIES="${JOB_MAX_RETRIES:-1}"
ALL_TARGETS="news sports travel football"

usage() {
  echo "Usage: $0 <all|news|sports|travel|football>"
  echo ""
  echo "Required env: GCP_PROJECT_ID"
  echo "Optional env: GCP_REGION, AR_REPO, JOB_PREFIX, JOB_TASK_TIMEOUT, JOB_MAX_RETRIES"
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

job_name() {
  echo "${JOB_PREFIX}-$1-worker"
}

image_ref() {
  local service
  case "$1" in
    news) service="nexo-news-rag" ;;
    sports) service="nexo-sports-rag" ;;
    travel) service="nexo-travel-rag" ;;
    football) service="nexo-football-live" ;;
  esac
  echo "${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${service}:latest"
}

job_args() {
  case "$1" in
    news) echo "python ingest.py" ;;
    sports) echo "python worker.py" ;;
    travel) echo "python worker.py" ;;
    football) echo "python worker.py" ;;
  esac
}

job_env_vars() {
  case "$1" in
    news)
      echo "VECTOR_STORE_BACKEND=pgvector,VECTOR_STORE_DURABLE=true,PGVECTOR_SCHEMA=rag_news,LLM_MODEL=vertex_ai/gemini-2.5-flash,EMBEDDING_MODEL=vertex_ai/text-embedding-004,VERTEXAI_PROJECT=${GCP_PROJECT_ID},VERTEXAI_LOCATION=${REGION}"
      ;;
    sports)
      echo "VECTOR_STORE_BACKEND=pgvector,VECTOR_STORE_DURABLE=true,PGVECTOR_SCHEMA=rag_sports,SPORTS_WORKER_MODE=live,LLM_MODEL=vertex_ai/gemini-2.5-flash,EMBEDDING_MODEL=vertex_ai/text-embedding-004,VERTEXAI_PROJECT=${GCP_PROJECT_ID},VERTEXAI_LOCATION=${REGION}"
      ;;
    travel)
      echo "VECTOR_STORE_BACKEND=pgvector,VECTOR_STORE_DURABLE=true,PGVECTOR_SCHEMA=rag_travel,LLM_MODEL=vertex_ai/gemini-2.5-flash,EMBEDDING_MODEL=vertex_ai/text-embedding-004,VERTEXAI_PROJECT=${GCP_PROJECT_ID},VERTEXAI_LOCATION=${REGION}"
      ;;
    football)
      echo "VECTOR_STORE_BACKEND=pgvector,VECTOR_STORE_DURABLE=true,PGVECTOR_SCHEMA=rag_football,FOOTBALL_WORKER_MODE=live,LLM_MODEL=vertex_ai/gemini-2.5-flash,EMBEDDING_MODEL=vertex_ai/text-embedding-004,VERTEXAI_PROJECT=${GCP_PROJECT_ID},VERTEXAI_LOCATION=${REGION}"
      ;;
  esac
}

job_secrets() {
  case "$1" in
    news) echo "PGVECTOR_DSN=NEXO_PGVECTOR_DSN:latest" ;;
    sports) echo "PGVECTOR_DSN=NEXO_PGVECTOR_DSN:latest,FOOTBALL_DATA_API_KEY=FOOTBALL_DATA_API_KEY:latest" ;;
    travel) echo "PGVECTOR_DSN=NEXO_PGVECTOR_DSN:latest" ;;
    football) echo "PGVECTOR_DSN=NEXO_PGVECTOR_DSN:latest,FOOTBALL_DATA_API_KEY=FOOTBALL_DATA_API_KEY:latest" ;;
  esac
}

create_or_update_job() {
  local target="$1"
  local name
  name="$(job_name "$target")"
  local image
  image="$(image_ref "$target")"
  local cmdline
  cmdline="$(job_args "$target")"
  local envs
  envs="$(job_env_vars "$target")"
  local secrets
  secrets="$(job_secrets "$target")"

  echo "Configuring ${name}"
  echo "  Image: ${image}"
  echo "  Command: ${cmdline}"

  local job_flags=(
    "${name}"
    "--image=${image}"
    "--set-cloudsql-instances=${GCP_PROJECT_ID}:${REGION}:nexo-platform-pg"
    "--set-env-vars=${envs}"
    "--set-secrets=${secrets}"
    "--max-retries=${JOB_MAX_RETRIES}"
    "--tasks=1"
    "--task-timeout=${JOB_TASK_TIMEOUT}"
    "--memory=1Gi"
    "--cpu=1"
    "--command=python"
  )

  local arg
  for arg in $cmdline; do
    if [[ "$arg" != "python" ]]; then
      job_flags+=("--args=${arg}")
    fi
  done

  if gcloud run jobs describe "$name" --project "${GCP_PROJECT_ID}" --region "${REGION}" >/dev/null 2>&1; then
    gcloud run jobs update \
      --project "${GCP_PROJECT_ID}" \
      --region "${REGION}" \
      "${job_flags[@]}"
  else
    gcloud run jobs create \
      --project "${GCP_PROJECT_ID}" \
      --region "${REGION}" \
      "${job_flags[@]}"
  fi
}

echo "=== Configure RAG Worker Jobs ==="
echo "Project: ${GCP_PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Target:  ${targets}"
echo ""

for t in $targets; do
  create_or_update_job "$t"
done

echo ""
echo "Done. Current jobs in ${REGION}:"
gcloud run jobs list --project "${GCP_PROJECT_ID}" --region "${REGION}" \
  --format='table(metadata.name,spec.template.template.spec.containers[0].image,status.conditions[0].state)'
