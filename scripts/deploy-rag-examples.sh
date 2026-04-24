#!/usr/bin/env bash
#
# Deploy RAG partner examples to Cloud Run via Cloud Build.
#
# Usage:
#   ./scripts/deploy-rag-examples.sh <target> [--dry-run]
#
# Targets: all, news, sports, travel, football
#
# Required environment variables:
#   GCP_PROJECT_ID   GCP project ID
#
# Optional environment variables:
#   GCP_REGION       Cloud Run region (default: europe-west1)
#   AR_REPO          Artifact Registry repo name (default: nexo-examples)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REGION="${GCP_REGION:-europe-west1}"
AR_REPO="${AR_REPO:-nexo-examples}"
DRY_RUN=false

get_service_name() {
  case "$1" in
    news)   echo "nexo-news-rag" ;;
    sports) echo "nexo-sports-rag" ;;
    travel) echo "nexo-travel-rag" ;;
  esac
}

get_example_dir() {
  case "$1" in
    news)   echo "examples/webhook/news-rag/python" ;;
    sports) echo "examples/webhook/sports-rag/python" ;;
    travel) echo "examples/webhook/travel-rag/python" ;;
  esac
}

ALL_TARGETS="news sports travel"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
usage() {
  echo "Usage: $0 <all|news|sports|travel> [--dry-run]"
  echo ""
  echo "Required env: GCP_PROJECT_ID"
  echo "Optional env: GCP_REGION (default: europe-west1), AR_REPO (default: nexo-examples)"
  exit 1
}

deploy_example() {
  local target="$1"
  local service_name
  service_name="$(get_service_name "$target")"
  local example_dir
  example_dir="$(get_example_dir "$target")"
  local config_path="${REPO_ROOT}/${example_dir}/cloudbuild.yaml"

  if [[ ! -f "$config_path" ]]; then
    echo "ERROR: cloudbuild.yaml not found at ${config_path}"
    return 1
  fi

  if [[ "$DRY_RUN" == true ]]; then
    echo "[DRY RUN] Would deploy: ${target}"
    echo "  Service:  ${service_name}"
    echo "  Config:   ${example_dir}/cloudbuild.yaml"
    echo "  Command:  gcloud builds submit --config ${example_dir}/cloudbuild.yaml --substitutions _PROJECT_ID=${GCP_PROJECT_ID},_REGION=${REGION},_SERVICE_NAME=${service_name},_AR_REPO=${AR_REPO}"
    echo ""
  else
    echo "Deploying ${target} (${service_name})..."
    cd "$REPO_ROOT"
    local image_tag
    image_tag="$(date +%Y%m%d-%H%M%S)"
    gcloud builds submit \
      --config "${example_dir}/cloudbuild.yaml" \
      --substitutions "_PROJECT_ID=${GCP_PROJECT_ID},_REGION=${REGION},_SERVICE_NAME=${service_name},_AR_REPO=${AR_REPO},_IMAGE_TAG=${image_tag}"
    echo "Done: ${target}"
    echo ""
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  usage
fi

TARGET="$1"
shift

# Parse flags
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

# Validate environment
if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID environment variable is required."
  echo ""
  usage
fi

# Resolve targets
case "$TARGET" in
  all)
    targets="$ALL_TARGETS"
    ;;
  news|sports|travel)
    targets="$TARGET"
    ;;
  *)
    echo "ERROR: Unknown target '${TARGET}'"
    usage
    ;;
esac

echo "=== RAG Example Deployment ==="
echo "Project:  ${GCP_PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Targets:  ${targets}"
if [[ "$DRY_RUN" == true ]]; then
  echo "Mode:     DRY RUN"
fi
echo ""

for t in $targets; do
  deploy_example "$t"
done

echo "=== Complete ==="
