#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTEST_BIN="${ROOT_DIR}/.venv/bin/pytest"

if [[ ! -x "$PYTEST_BIN" ]]; then
  echo "ERROR: ${PYTEST_BIN} not found. Run 'make setup-dev' first."
  exit 1
fi

echo "==> pytest in examples/hosted/python"
(
  cd "${ROOT_DIR}/examples/hosted/python"
  "$PYTEST_BIN" -q
)

echo "==> node tests in examples/hosted/typescript"
(
  cd "${ROOT_DIR}/examples/hosted/typescript"
  node --test test-server.mjs
)
