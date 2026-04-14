#!/usr/bin/env bash
set -euo pipefail

# Resolve base URL: flag > env var > default (production)
case "${1:-}" in
  --staging) BASE="${NEXO_BASE_URL:-https://staging.nexo.luzia.com}" ;;
  --local)   BASE="${NEXO_BASE_URL:-http://localhost:8000}" ;;
  *)         BASE="${NEXO_BASE_URL:-https://nexo.luzia.com}" ;;
esac

: "${NEXO_DEVELOPER_KEY:?Set NEXO_DEVELOPER_KEY in your environment (get it from ${BASE}/dashboard/profile)}"

# Remove existing connection if present, then add fresh
claude mcp remove nexo-mcp 2>/dev/null || true
claude mcp add --transport http --header "X-Api-Key: ${NEXO_DEVELOPER_KEY}" \
  nexo-mcp "${BASE}/mcp"

echo "Connected to ${BASE}/mcp"
echo "Open Claude Code and start building."
