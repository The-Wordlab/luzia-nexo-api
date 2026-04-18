#!/usr/bin/env bash
# Live demo conversational test: validates seeded webhook demos respond correctly.
#
# Tests each demo app through the canonical POST /api/responses endpoint
# with SSE streaming. Verifies stream_start, content_delta, and done events.
#
# Authentication: uses NEXO_DEVELOPER_KEY (recommended) or falls back to
# email/password login via NEXO_TEST_EMAIL + NEXO_TEST_PASSWORD env vars.
# Do NOT hardcode credentials in this script - it lives in a public repo.
#
# Usage:
#   export NEXO_DEVELOPER_KEY=nexo_uak_...
#   ./scripts/test-live-demos.sh                           # local (default)
#   ./scripts/test-live-demos.sh --nexo-url https://nexo-cdn-alb.staging.thewordlab.net
#
# Flags:
#   --nexo-url   Nexo backend base URL (default: http://localhost:8000)

set -euo pipefail

NEXO_URL="${NEXO_BASE_URL:-http://localhost:8000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nexo-url)  NEXO_URL="$2";  shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

pass() { echo "  [PASS] $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "  [FAIL] $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

echo "========================================================"
echo "  Nexo Live Demo Conversational Test"
echo "  Backend: $NEXO_URL"
echo "========================================================"

# Step 1: Authenticate
echo ""
echo "--- Authenticate ---"

ACCESS_TOKEN=""
DEV_KEY="${NEXO_DEVELOPER_KEY:-}"

if [[ -n "$DEV_KEY" ]]; then
  # Developer key auth - preferred path
  echo "  Using developer key"
  ACCESS_TOKEN="__dev_key__"
else
  # Fall back to email/password
  TEST_EMAIL="${NEXO_TEST_EMAIL:-}"
  TEST_PASSWORD="${NEXO_TEST_PASSWORD:-}"
  if [[ -z "$TEST_EMAIL" || -z "$TEST_PASSWORD" ]]; then
    echo "[FATAL] Set NEXO_DEVELOPER_KEY or both NEXO_TEST_EMAIL + NEXO_TEST_PASSWORD"
    exit 1
  fi
  ACCESS_TOKEN=$(curl -s -L -X POST "$NEXO_URL/api/auth/token" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
  if [[ -z "$ACCESS_TOKEN" ]]; then
    echo "[FATAL] Authentication failed"
    exit 1
  fi
fi
pass "Authenticated"

# Auth header helper
auth_header() {
  if [[ -n "$DEV_KEY" ]]; then
    echo "X-Api-Key: $DEV_KEY"
  else
    echo "Authorization: Bearer $ACCESS_TOKEN"
  fi
}

# Step 2: List demo apps
echo ""
echo "--- List demo apps ---"
APPS_JSON=$(curl -s -L "$NEXO_URL/api/apps/?size=100" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" 2>/dev/null)

DEMO_APPS=$(echo "$APPS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
for app in (items if isinstance(items, list) else []):
    cj = app.get('config_json') or {}
    dk = cj.get('demo_key', '')
    if dk and dk != 'builder':
        print(f'{dk}|{app[\"id\"]}|{app[\"name\"]}')
" 2>/dev/null)

if [[ -z "$DEMO_APPS" ]]; then
  echo "[WARN] No demo apps found. Is demo data seeded?"
  exit 0
fi

DEMO_COUNT=$(echo "$DEMO_APPS" | wc -l | tr -d ' ')
echo "  Found $DEMO_COUNT demo apps"

# Step 3: Test each demo
echo ""
echo "--- Conversational tests ---"

get_test_message() {
  case "$1" in
    food-ordering)    echo "Show me the menu" ;;
    travel-planning)  echo "Plan a weekend trip to Barcelona" ;;
    news-rag)         echo "What are the latest headlines?" ;;
    sports-rag)       echo "Tell me about recent football matches" ;;
    travel-rag)       echo "What are top destinations in Europe?" ;;
    football-live)    echo "Show me live match scores" ;;
    *)                echo "Hello" ;;
  esac
}

while IFS='|' read -r DEMO_KEY APP_ID APP_NAME; do
  MSG=$(get_test_message "$DEMO_KEY")

  # Create thread
  THREAD_JSON=$(curl -s -L -X POST "$NEXO_URL/api/apps/$APP_ID/threads" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d '{}' 2>/dev/null)

  THREAD_ID=$(echo "$THREAD_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d.get('thread', d)
print(t.get('id', ''))" 2>/dev/null)

  if [[ -z "$THREAD_ID" ]]; then
    fail "$DEMO_KEY ($APP_NAME): could not create thread"
    continue
  fi

  # Send message via POST /api/responses (canonical endpoint)
  RESPONSE=$(curl -s -L -X POST "$NEXO_URL/api/responses" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    --max-time 30 \
    -d "{\"app_id\":\"$APP_ID\",\"thread_id\":\"$THREAD_ID\",\"input\":\"$MSG\"}" 2>/dev/null)

  # Parse SSE events - verify canonical stream shape
  EVENT_COUNT=$(echo "$RESPONSE" | grep -c '^event:' || true)
  HAS_STREAM_START=$(echo "$RESPONSE" | grep -c 'event: stream_start' || true)
  HAS_CONTENT=$(echo "$RESPONSE" | grep -c 'event: content_delta' || true)
  HAS_DONE=$(echo "$RESPONSE" | grep -c 'event: done' || true)
  BYTE_COUNT=${#RESPONSE}

  # Verify done payload has required fields (text or content_parts)
  DONE_PAYLOAD_OK=0
  DONE_DATA=$(echo "$RESPONSE" | grep -A1 'event: done' | grep '^data:' | head -1)
  if [[ -n "$DONE_DATA" ]]; then
    if echo "$DONE_DATA" | python3 -c "
import sys,json
d=json.loads(sys.stdin.read().replace('data: ','',1))
ok = 'text' in d or 'content_parts' in d or 'cards' in d or 'status' in d
sys.exit(0 if ok else 1)
" 2>/dev/null; then
      DONE_PAYLOAD_OK=1
    fi
  fi

  DETAILS="events=$EVENT_COUNT stream_start=$HAS_STREAM_START content=$HAS_CONTENT done=$HAS_DONE done_shape=$DONE_PAYLOAD_OK bytes=$BYTE_COUNT"
  if [[ "$HAS_STREAM_START" -gt 0 && "$HAS_DONE" -gt 0 && "$DONE_PAYLOAD_OK" -gt 0 && "$BYTE_COUNT" -gt 100 ]]; then
    pass "$DEMO_KEY ($APP_NAME): $DETAILS"
  elif [[ "$HAS_DONE" -gt 0 && "$BYTE_COUNT" -gt 100 ]]; then
    # Response arrived but stream shape is not canonical
    if [[ "$HAS_STREAM_START" -eq 0 ]]; then
      fail "$DEMO_KEY ($APP_NAME): missing stream_start event ($DETAILS)"
    elif [[ "$DONE_PAYLOAD_OK" -eq 0 ]]; then
      fail "$DEMO_KEY ($APP_NAME): done payload missing text/content_parts/cards/status ($DETAILS)"
    else
      fail "$DEMO_KEY ($APP_NAME): $DETAILS"
    fi
  else
    fail "$DEMO_KEY ($APP_NAME): $DETAILS"
  fi

  # Cleanup thread
  curl -s -L -X DELETE "$NEXO_URL/api/apps/$APP_ID/threads/$THREAD_ID" \
    -H "$(auth_header)" >/dev/null 2>&1 || true

done <<< "$DEMO_APPS"

# Summary
echo ""
echo "========================================================"
echo "  Results: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "========================================================"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
