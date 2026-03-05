#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_pytest() {
  local dir="$1"
  echo "==> pytest in ${dir}"
  (
    cd "${ROOT_DIR}/${dir}"
    pytest -q
  )
}

run_pytest "examples/webhook/minimal/python"
run_pytest "examples/webhook/structured/python"
run_pytest "examples/webhook/advanced/python"

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
