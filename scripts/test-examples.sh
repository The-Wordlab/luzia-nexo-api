#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTEST_BIN="${ROOT_DIR}/.venv/bin/pytest"

if [[ ! -x "$PYTEST_BIN" ]]; then
  echo "ERROR: ${PYTEST_BIN} not found. Run 'make setup-dev' first."
  exit 1
fi

run_pytest() {
  local dir="$1"
  echo "==> pytest in ${dir}"
  (
    cd "${ROOT_DIR}/${dir}"
    "$PYTEST_BIN" -q
  )
}

run_pytest "examples/webhook/minimal/python"
run_pytest "examples/webhook/structured/python"
run_pytest "examples/webhook/advanced/python"
run_pytest "examples/webhook/fitness-coach/python"
run_pytest "examples/webhook/travel-planner/python"
run_pytest "examples/webhook/language-tutor/python"

echo "==> node tests in examples/webhook/minimal/typescript"
(
  cd "${ROOT_DIR}/examples/webhook/minimal/typescript"
  node --test test-webhook-server.mjs
)

echo "==> node tests in examples/webhook/openclaw-bridge/typescript"
(
  cd "${ROOT_DIR}/examples/webhook/openclaw-bridge/typescript"
  node --test test-openclaw-bridge-server.mjs
)
