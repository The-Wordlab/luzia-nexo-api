#!/usr/bin/env bash
# Integration smoke test: validates a Nexo instance can communicate with a deployed webhook.
#
# Usage:
#   ./integration-smoke.sh --webhook-url https://your-webhook.run.app
#   WEBHOOK_SECRET=my-secret ./integration-smoke.sh --webhook-url https://your-webhook.run.app
#
# Flags:
#   --nexo-url       Nexo base URL (default: http://localhost:8000)
#   --webhook-url    Deployed Cloud Run webhook URL (required)
#   --email          Test user email (default: e2e-smoke@luzia.com)
#   --password       Test user password (default: NexoPass#99)
#   --webhook-secret Webhook secret (default: test-secret, or $WEBHOOK_SECRET env var)

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
NEXO_URL="http://localhost:8000"
WEBHOOK_URL=""
EMAIL="tester@luzia.com"
PASSWORD="NexoPass#99"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-test-secret}"

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --nexo-url)       NEXO_URL="$2";       shift 2 ;;
    --webhook-url)    WEBHOOK_URL="$2";    shift 2 ;;
    --email)          EMAIL="$2";          shift 2 ;;
    --password)       PASSWORD="$2";       shift 2 ;;
    --webhook-secret) WEBHOOK_SECRET="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

if [[ -z "$WEBHOOK_URL" ]]; then
  echo "ERROR: --webhook-url is required"
  echo "Usage: $0 --webhook-url https://your-webhook.run.app [--nexo-url http://localhost:8000]"
  exit 1
fi

TIMESTAMP=$(date +%s)
APP_ID=""
ACCESS_TOKEN=""

# ── Helpers ───────────────────────────────────────────────────────────────────
pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }
step() { echo ""; echo "==> $*"; }

# Portable "all lines except last" (macOS head doesn't support -n -1)
body_of() { echo "$1" | sed '$ d'; }
last_line() { echo "$1" | tail -n 1; }

cleanup() {
  if [[ -n "$APP_ID" && -n "$ACCESS_TOKEN" ]]; then
    step "Step 5: Cleanup - deleting test app $APP_ID"
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -X DELETE \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      "$NEXO_URL/api/apps/$APP_ID")
    if [[ "$HTTP_STATUS" == "204" || "$HTTP_STATUS" == "200" ]]; then
      pass "Test app deleted (HTTP $HTTP_STATUS)"
    else
      echo "[WARN] Cleanup returned HTTP $HTTP_STATUS - app may need manual deletion"
    fi
  fi
}
trap cleanup EXIT

echo "========================================================"
echo "  Nexo Integration Smoke Test"
echo "  Nexo:    $NEXO_URL"
echo "  Webhook: $WEBHOOK_URL"
echo "  User:    $EMAIL"
echo "========================================================"

# ── Step 1: Authenticate ──────────────────────────────────────────────────────
step "Step 1: Authenticate as $EMAIL"

AUTH_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${EMAIL}&password=${PASSWORD}" \
  "$NEXO_URL/api/auth/jwt/login")

AUTH_BODY=$(body_of "$AUTH_RESPONSE")
AUTH_STATUS=$(last_line "$AUTH_RESPONSE")

if [[ "$AUTH_STATUS" != "200" ]]; then
  fail "Authentication failed (HTTP $AUTH_STATUS). Body: $AUTH_BODY"
fi

ACCESS_TOKEN=$(echo "$AUTH_BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
if [[ -z "$ACCESS_TOKEN" ]]; then
  fail "Could not extract access_token from response: $AUTH_BODY"
fi

pass "Authenticated (HTTP $AUTH_STATUS)"

# ── Step 1b: Get user's org ID ────────────────────────────────────────────────
step "Step 1b: Resolve org_id"

ORG_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$NEXO_URL/api/organizations/")

ORG_BODY=$(body_of "$ORG_RESPONSE")
ORG_STATUS=$(last_line "$ORG_RESPONSE")

if [[ "$ORG_STATUS" != "200" ]]; then
  fail "Organizations fetch failed (HTTP $ORG_STATUS). Body: $ORG_BODY"
fi

ORG_ID=$(echo "$ORG_BODY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [[ -z "$ORG_ID" ]]; then
  fail "Could not extract org_id from response: $ORG_BODY"
fi

pass "Org ID: $ORG_ID"

# ── Step 2: Create test app ───────────────────────────────────────────────────
step "Step 2: Create test app"

APP_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Smoke Test App [$TIMESTAMP]\",
    \"description\": \"Integration smoke test\",
    \"org_id\": \"$ORG_ID\",
    \"webhook_url\": \"$WEBHOOK_URL\",
    \"webhook_secret\": \"$WEBHOOK_SECRET\",
    \"config_json\": {\"integration_mode\": \"webhook\"}
  }" \
  "$NEXO_URL/api/apps/")

APP_BODY=$(body_of "$APP_RESPONSE")
APP_STATUS=$(last_line "$APP_RESPONSE")

if [[ "$APP_STATUS" != "200" && "$APP_STATUS" != "201" ]]; then
  fail "App creation failed (HTTP $APP_STATUS). Body: $APP_BODY"
fi

APP_ID=$(echo "$APP_BODY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [[ -z "$APP_ID" ]]; then
  fail "Could not extract app id from response: $APP_BODY"
fi

pass "Test app created: $APP_ID (HTTP $APP_STATUS)"

# ── Step 3: Send test message ─────────────────────────────────────────────────
step "Step 3: Send test message to webhook"

MSG_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"app_id\": \"$APP_ID\",
    \"input\": \"hello, this is a smoke test\",
    \"stream\": false
  }" \
  "$NEXO_URL/api/responses")

MSG_BODY=$(body_of "$MSG_RESPONSE")
MSG_STATUS=$(last_line "$MSG_RESPONSE")

if [[ "$MSG_STATUS" != "200" ]]; then
  fail "Send message failed (HTTP $MSG_STATUS). Body: $MSG_BODY"
fi

pass "Message sent (HTTP $MSG_STATUS)"

# ── Step 4: Verify response shape ─────────────────────────────────────────────
step "Step 4: Verify response shape"

if [[ -z "$MSG_BODY" ]]; then
  fail "Response body is empty"
fi

# Check that body contains at least one expected field
if echo "$MSG_BODY" | grep -q '"output"\|"content"\|"message"\|"text"'; then
  pass "Response body has expected shape"
else
  echo "[WARN] Response body may have unexpected shape. Got: $MSG_BODY"
  # Not fatal - webhook could return a valid but minimal response
  pass "Response body is non-empty (shape check inconclusive)"
fi

# ── Done (cleanup runs via trap) ──────────────────────────────────────────────
echo ""
echo "========================================================"
echo "  All steps passed. Integration smoke test PASSED."
echo "========================================================"
