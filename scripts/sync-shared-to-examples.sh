#!/usr/bin/env bash
# Copy shared/ utilities into each example's python directory
# so Docker builds and Cloud Run source deploys include them.
#
# Run before deploying: ./scripts/sync-shared-to-examples.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SHARED_DIR="${REPO_ROOT}/examples/webhook/shared"

if [[ ! -d "${SHARED_DIR}" ]]; then
  echo "ERROR: ${SHARED_DIR} not found"
  exit 1
fi

EXAMPLES=(
  food-ordering
  news-rag
  travel-rag
  sports-rag
  routines
  travel-planning
)

for example in "${EXAMPLES[@]}"; do
  target="${REPO_ROOT}/examples/webhook/${example}/python/shared"
  rm -rf "${target}"
  cp -r "${SHARED_DIR}" "${target}"
  echo "Synced shared/ -> ${example}/python/shared/"
done

echo "Done. ${#EXAMPLES[@]} examples updated."
