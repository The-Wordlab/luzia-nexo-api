#!/usr/bin/env bash
#
# Verify that deployed RAG Cloud Run services and Cloud Run Jobs stay aligned.
#
# Checks per target:
# - service URL and latest ready revision
# - deployed service image
# - worker job image
# - PGVECTOR_SCHEMA, LLM_MODEL, EMBEDDING_MODEL env alignment
# - latest worker execution status/timestamp
#
# Usage:
#   GCP_PROJECT_ID=<project> ./scripts/check-rag-worker-sync.sh

set -euo pipefail

REGION="${GCP_REGION:-europe-west1}"

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required"
  exit 2
fi

targets=(news sports travel)

service_name() {
  case "$1" in
    news) echo "nexo-news-rag" ;;
    sports) echo "nexo-sports-rag" ;;
    travel) echo "nexo-travel-rag" ;;
  esac
}

job_name() {
  case "$1" in
    news) echo "nexo-rag-news-worker" ;;
    sports) echo "nexo-rag-sports-worker" ;;
    travel) echo "nexo-rag-travel-worker" ;;
  esac
}

extract_env_value() {
  local json="$1"
  local key="$2"
  python3 - "$json" "$key" <<'PYEOF'
import json
import sys

payload = json.loads(sys.argv[1])
key = sys.argv[2]
for entry in payload:
    if entry.get("name") == key:
        print(entry.get("value", ""))
        break
PYEOF
}

echo "=== Check RAG Worker Sync ==="
echo "Project: ${GCP_PROJECT_ID}"
echo "Region:  ${REGION}"
echo ""

fail=0

for target in "${targets[@]}"; do
  service="$(service_name "$target")"
  job="$(job_name "$target")"

  service_json="$(gcloud run services describe "$service" \
    --project "$GCP_PROJECT_ID" \
    --region "$REGION" \
    --format=json)"
  job_json="$(gcloud run jobs describe "$job" \
    --project "$GCP_PROJECT_ID" \
    --region "$REGION" \
    --format=json)"

  service_url="$(printf '%s' "$service_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"]["url"])')"
  service_revision="$(printf '%s' "$service_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"]["latestReadyRevisionName"])')"
  service_image="$(printf '%s' "$service_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0]["image"])')"
  service_env_json="$(printf '%s' "$service_json" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0].get("env", [])))')"

  job_image="$(printf '%s' "$job_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"])')"
  job_env_json="$(printf '%s' "$job_json" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["spec"]["template"]["spec"]["template"]["spec"]["containers"][0].get("env", [])))')"
  job_exec_status="$(printf '%s' "$job_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"].get("latestCreatedExecution", {}).get("completionStatus", ""))')"
  job_exec_timestamp="$(printf '%s' "$job_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"].get("latestCreatedExecution", {}).get("completionTimestamp", ""))')"

  service_schema="$(extract_env_value "$service_env_json" "PGVECTOR_SCHEMA")"
  service_llm_model="$(extract_env_value "$service_env_json" "LLM_MODEL")"
  service_embedding_model="$(extract_env_value "$service_env_json" "EMBEDDING_MODEL")"
  job_schema="$(extract_env_value "$job_env_json" "PGVECTOR_SCHEMA")"
  job_llm_model="$(extract_env_value "$job_env_json" "LLM_MODEL")"
  job_embedding_model="$(extract_env_value "$job_env_json" "EMBEDDING_MODEL")"

  echo "${target}:"
  echo "  service: ${service}"
  echo "  url: ${service_url}"
  echo "  revision: ${service_revision}"
  echo "  service image: ${service_image}"
  echo "  worker image:  ${job_image}"
  echo "  schema:        service=${service_schema} worker=${job_schema}"
  echo "  llm model:     service=${service_llm_model} worker=${job_llm_model}"
  echo "  embed model:   service=${service_embedding_model} worker=${job_embedding_model}"
  echo "  latest worker: ${job_exec_status:-unknown} at ${job_exec_timestamp:-unknown}"

  if [[ "$service_image" != "$job_image" ]] || \
     [[ "$service_schema" != "$job_schema" ]] || \
     [[ "$service_llm_model" != "$job_llm_model" ]] || \
     [[ "$service_embedding_model" != "$job_embedding_model" ]]; then
    echo "  [FAIL] worker/service drift detected"
    fail=1
  else
    echo "  [OK] worker/service aligned"
  fi
  echo ""
done

if [[ "$fail" -ne 0 ]]; then
  echo "RAG worker sync check failed"
  exit 1
fi

echo "RAG worker sync check passed"
