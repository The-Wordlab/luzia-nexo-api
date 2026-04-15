#!/usr/bin/env bash
set -euo pipefail

# Resolve base URL: explicit flag > env var.
case "${1:-}" in
  --staging) BASE="${NEXO_BASE_URL:-https://nexo-cdn-alb.staging.thewordlab.net}" ;;
  --local)   BASE="${NEXO_BASE_URL:-http://localhost:8000}" ;;
  "")        BASE="${NEXO_BASE_URL:-}" ;;
  *)
    echo "Usage: $0 [--local|--staging]" >&2
    exit 1
    ;;
esac

BASE="${BASE%/}"

: "${BASE:?Set NEXO_BASE_URL or use --local/--staging. Hosted MCP base URLs are environment-specific.}"
: "${NEXO_DEVELOPER_KEY:?Set NEXO_DEVELOPER_KEY in your environment (get it from ${BASE}/dashboard/profile)}"

# Remove existing connection if present, then add fresh
claude mcp remove --scope project nexo-mcp 2>/dev/null || true
claude mcp add --scope project --transport http nexo-mcp "${BASE}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"

echo "Connected to ${BASE}/mcp"
echo "Open Claude Code and start building."
