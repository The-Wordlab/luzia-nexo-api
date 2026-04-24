#!/usr/bin/env bash
# Run RAG example test suites in sequence.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTEST_BIN="${REPO_ROOT}/.venv/bin/pytest"

if [[ ! -x "$PYTEST_BIN" ]]; then
  echo "ERROR: ${PYTEST_BIN} not found. Create .venv and install deps first."
  exit 1
fi

run_suite() {
  local dir="$1"
  local test_file="$2"
  echo "==> ${dir}/${test_file}"
  (
    cd "${REPO_ROOT}/${dir}"
    "$PYTEST_BIN" -q "$test_file"
  )
}

run_suite "examples/webhook/news-rag/python" "test_news_rag.py"
run_suite "examples/webhook/sports-rag/python" "test_sports_rag.py"
run_suite "examples/webhook/travel-rag/python" "test_travel_rag.py"

echo "RAG test suites passed"
