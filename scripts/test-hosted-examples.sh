#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> pytest in examples/hosted/python"
(
  cd "${ROOT_DIR}/examples/hosted/python"
  pytest -q
)

echo "==> node tests in examples/hosted/typescript"
(
  cd "${ROOT_DIR}/examples/hosted/typescript"
  node --test test-server.mjs
)
