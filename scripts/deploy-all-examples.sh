#!/usr/bin/env bash
#
# Deploy all server-side examples to Cloud Run.
#
# Excludes client-only proactive scripts by design.
#
# Usage:
#   ./scripts/deploy-all-examples.sh all [--dry-run]
#   ./scripts/deploy-all-examples.sh minimal-py [--dry-run]
#
# Targets:
#   all
#   hosted
#   rag
#   minimal-py
#   structured-py
#   advanced-py
#   minimal-ts
#   openclaw-bridge
#   hosted-py
#   hosted-ts
#   demo-receiver
#   news
#   sports
#   travel
#   football
#   routines
#   food-ordering
#   travel-planning

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-europe-west1}"
DRY_RUN=false

# OpenClaw bridge runtime config (required for openclaw-bridge target).
OPENCLAW_BASE_URL="${OPENCLAW_BASE_URL:-}"
OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID:-main}"

usage() {
  echo "Usage: $0 <target> [--dry-run]"
  echo ""
  echo "Targets:"
  echo "  all | hosted | rag"
  echo "  minimal-py | structured-py | advanced-py | minimal-ts | openclaw-bridge"
  echo "  hosted-py | hosted-ts | demo-receiver"
  echo "  news | sports | travel | football | routines | food-ordering | travel-planning"
  echo ""
  echo "Required env: GCP_PROJECT_ID"
  echo "Optional env: GCP_REGION (default: europe-west1)"
  echo "OpenClaw target env: OPENCLAW_BASE_URL (required for openclaw-bridge), OPENCLAW_AGENT_ID (default: main)"
  exit 1
}

require_project() {
  if [[ -z "${PROJECT_ID}" ]]; then
    echo "ERROR: GCP_PROJECT_ID is required."
    usage
  fi
}

run_cmd() {
  if [[ "${DRY_RUN}" == true ]]; then
    echo "[DRY RUN] $*"
  else
    eval "$@"
  fi
}

deploy_source_service() {
  local service_name="$1"
  local source_dir="$2"
  local extra_args="$3"

  local cmd
  cmd="gcloud run deploy \"${service_name}\" \
    --project \"${PROJECT_ID}\" \
    --region \"${REGION}\" \
    --source \"${source_dir}\" \
    --allow-unauthenticated \
    ${extra_args} \
    --quiet"

  run_cmd "${cmd}"
}

deploy_minimal_py() {
  deploy_source_service \
    "nexo-webhook-minimal-py" \
    "${REPO_ROOT}/examples/webhook/minimal/python" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_structured_py() {
  deploy_source_service \
    "nexo-webhook-structured-py" \
    "${REPO_ROOT}/examples/webhook/structured/python" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_advanced_py() {
  deploy_source_service \
    "nexo-webhook-advanced-py" \
    "${REPO_ROOT}/examples/webhook/advanced/python" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_minimal_ts() {
  deploy_source_service \
    "nexo-webhook-minimal-ts" \
    "${REPO_ROOT}/examples/webhook/minimal/typescript" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_openclaw_bridge() {
  if [[ -z "${OPENCLAW_BASE_URL}" ]]; then
    echo "ERROR: OPENCLAW_BASE_URL is required for openclaw-bridge deployment."
    exit 1
  fi
  deploy_source_service \
    "nexo-openclaw-bridge" \
    "${REPO_ROOT}/examples/webhook/openclaw-bridge/typescript" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest,OPENCLAW_GATEWAY_TOKEN=OPENCLAW_GATEWAY_TOKEN:latest,OPENCLAW_ORIGIN_HEADER_VALUE=OPENCLAW_ORIGIN_HEADER_VALUE:latest --set-env-vars OPENCLAW_BASE_URL=${OPENCLAW_BASE_URL},OPENCLAW_AGENT_ID=${OPENCLAW_AGENT_ID}"
}

deploy_routines() {
  deploy_source_service \
    "nexo-routines" \
    "${REPO_ROOT}/examples/webhook/routines/python" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_food_ordering() {
  deploy_source_service \
    "nexo-food-ordering" \
    "${REPO_ROOT}/examples/webhook/food-ordering/python" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_travel_planning() {
  deploy_source_service \
    "nexo-travel-planning" \
    "${REPO_ROOT}/examples/webhook/travel-planning/python" \
    "--clear-base-image --set-secrets WEBHOOK_SECRET=WEBHOOK_SECRET:latest"
}

deploy_hosted_py() {
  local cmd="cd \"${REPO_ROOT}\" && GCP_PROJECT_ID=\"${PROJECT_ID}\" GCP_REGION=\"${REGION}\" SERVICE_NAME=nexo-examples-py ./examples/hosted/python/deploy/cloudrun/deploy.sh"
  run_cmd "${cmd}"
}

deploy_hosted_ts() {
  local cmd="cd \"${REPO_ROOT}\" && GCP_PROJECT_ID=\"${PROJECT_ID}\" GCP_REGION=\"${REGION}\" SERVICE_NAME=nexo-examples-ts ./examples/hosted/typescript/deploy/cloudrun/deploy.sh"
  run_cmd "${cmd}"
}

deploy_demo_receiver() {
  local cmd="cd \"${REPO_ROOT}\" && GCP_PROJECT_ID=\"${PROJECT_ID}\" GCP_REGION=\"${REGION}\" SERVICE_NAME=nexo-demo-receiver ./examples/hosted/demo-receiver/deploy/cloudrun/deploy.sh"
  run_cmd "${cmd}"
}

deploy_rag_target() {
  local rag_target="$1"
  local cmd="cd \"${REPO_ROOT}\" && GCP_PROJECT_ID=\"${PROJECT_ID}\" GCP_REGION=\"${REGION}\" ./scripts/deploy-rag-examples.sh ${rag_target}"
  run_cmd "${cmd}"
}

run_target() {
  case "$1" in
    all)
      deploy_demo_receiver
      deploy_hosted_py
      deploy_hosted_ts
      deploy_minimal_py
      deploy_structured_py
      deploy_advanced_py
      deploy_minimal_ts
      deploy_openclaw_bridge
      deploy_routines
      deploy_food_ordering
      deploy_travel_planning
      deploy_rag_target all
      ;;
    hosted)
      deploy_demo_receiver
      deploy_hosted_py
      deploy_hosted_ts
      ;;
    rag)
      deploy_rag_target all
      ;;
    minimal-py) deploy_minimal_py ;;
    structured-py) deploy_structured_py ;;
    advanced-py) deploy_advanced_py ;;
    minimal-ts) deploy_minimal_ts ;;
    openclaw-bridge) deploy_openclaw_bridge ;;
    routines) deploy_routines ;;
    food-ordering) deploy_food_ordering ;;
    travel-planning) deploy_travel_planning ;;
    hosted-py) deploy_hosted_py ;;
    hosted-ts) deploy_hosted_ts ;;
    demo-receiver) deploy_demo_receiver ;;
    news|sports|travel|football) deploy_rag_target "$1" ;;
    *) echo "ERROR: unknown target '$1'"; usage ;;
  esac
}

if [[ $# -lt 1 ]]; then
  usage
fi

TARGET="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown flag: $1"
      usage
      ;;
  esac
done

require_project

echo "=== Deploy All Examples ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Target:  ${TARGET}"
if [[ "${DRY_RUN}" == true ]]; then
  echo "Mode:    DRY RUN"
fi
echo ""

run_target "${TARGET}"

echo ""
echo "=== Complete ==="
