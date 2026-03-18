#!/usr/bin/env bash
set -euo pipefail

# Smoke test for all deployed Cloud Run example services.
#
# Defaults:
#   GCP_PROJECT_ID=luzia-nexo-api-examples
#   GCP_REGION=europe-west1
#   RUN_INGEST=true
#   SMOKE_TIMEOUT_SECONDS=45
#
# Usage:
#   GCP_PROJECT_ID=<project> GCP_REGION=<region> ./scripts/smoke-live-services.sh

PROJECT_ID="${GCP_PROJECT_ID:-luzia-nexo-api-examples}"
REGION="${GCP_REGION:-europe-west1}"
RUN_INGEST="${RUN_INGEST:-true}"
TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-45}"

PASS_COUNT=0
FAIL_COUNT=0
FAILURES=()

require_bin() {
  local bin="$1"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $bin"
    exit 1
  fi
}

require_bin gcloud
require_bin curl
require_bin openssl
require_bin awk
require_bin sed
require_bin tr
require_bin head
require_bin jq

service_url() {
  local service="$1"
  gcloud run services describe "$service" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --format='value(status.url)'
}

record_pass() {
  local label="$1"
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "PASS: ${label}"
}

record_fail() {
  local label="$1"
  local detail="$2"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILURES+=("${label} :: ${detail}")
  echo "FAIL: ${label} :: ${detail}"
}

http_get_check() {
  local label="$1"
  local url="$2"
  local must_contain="${3:-}"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(curl -sS --max-time "$TIMEOUT_SECONDS" -o "$tmp" -w '%{http_code}' "$url" || true)"
  local body
  body="$(head -c 280 "$tmp" | tr '\n' ' ')"
  rm -f "$tmp"

  if [[ "$code" != "200" ]]; then
    record_fail "$label" "HTTP ${code}; body=${body}"
    return
  fi
  if [[ -n "$must_contain" ]] && [[ "$body" != *"$must_contain"* ]]; then
    record_fail "$label" "missing '${must_contain}' in body=${body}"
    return
  fi
  record_pass "$label"
}

http_get_expect_code_check() {
  local label="$1"
  local url="$2"
  local expected_code="$3"
  local must_contain="${4:-}"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(curl -sS --max-time "$TIMEOUT_SECONDS" -o "$tmp" -w '%{http_code}' "$url" || true)"
  local body
  body="$(head -c 280 "$tmp" | tr '\n' ' ')"
  rm -f "$tmp"

  if [[ "$code" != "$expected_code" ]]; then
    record_fail "$label" "HTTP ${code} (expected ${expected_code}); body=${body}"
    return
  fi
  if [[ -n "$must_contain" ]] && [[ "$body" != *"$must_contain"* ]]; then
    record_fail "$label" "missing '${must_contain}' in body=${body}"
    return
  fi
  record_pass "$label"
}

build_signature() {
  local raw="$1"
  local ts
  ts="$(date +%s)"
  local hash
  hash="$(printf "%s" "${ts}.${raw}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')"
  SIG_TIMESTAMP="$ts"
  SIG_VALUE="sha256=${hash}"
}

http_post_xsignature_check() {
  local label="$1"
  local url="$2"
  local payload="$3"
  local must_contain="${4:-schema_version}"
  local digest
  digest="$(printf "%s" "$payload" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(
    curl -sS --max-time "$TIMEOUT_SECONDS" -o "$tmp" -w '%{http_code}' \
      -X POST "$url" \
      -H 'Content-Type: application/json' \
      -H "X-Signature: ${digest}" \
      --data "$payload" || true
  )"
  local body
  body="$(head -c 320 "$tmp" | tr '\n' ' ')"
  rm -f "$tmp"

  if [[ "$code" != "200" ]]; then
    record_fail "$label" "HTTP ${code}; body=${body}"
    return
  fi
  if [[ -n "$must_contain" ]] && [[ "$body" != *"$must_contain"* ]]; then
    record_fail "$label" "missing '${must_contain}' in body=${body}"
    return
  fi
  record_pass "$label"
}

http_post_signed_check() {
  local label="$1"
  local url="$2"
  local payload="$3"
  local must_contain="${4:-schema_version}"

  build_signature "$payload"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(
    curl -sS --max-time "$TIMEOUT_SECONDS" -o "$tmp" -w '%{http_code}' \
      -X POST "$url" \
      -H 'Content-Type: application/json' \
      -H "X-Timestamp: ${SIG_TIMESTAMP}" \
      -H "X-Signature: ${SIG_VALUE}" \
      --data "$payload" || true
  )"
  local body
  body="$(head -c 320 "$tmp" | tr '\n' ' ')"
  rm -f "$tmp"

  if [[ "$code" != "200" ]]; then
    record_fail "$label" "HTTP ${code}; body=${body}"
    return
  fi
  if [[ -n "$must_contain" ]] && [[ "$body" != *"$must_contain"* ]]; then
    record_fail "$label" "missing '${must_contain}' in body=${body}"
    return
  fi
  record_pass "$label"
}

http_post_signed_prompt_suggestions_check() {
  local label="$1"
  local url="$2"
  local payload="$3"

  build_signature "$payload"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(
    curl -sS --max-time "$TIMEOUT_SECONDS" -o "$tmp" -w '%{http_code}' \
      -X POST "$url" \
      -H 'Content-Type: application/json' \
      -H "X-Timestamp: ${SIG_TIMESTAMP}" \
      -H "X-Signature: ${SIG_VALUE}" \
      --data "$payload" || true
  )"

  if [[ "$code" != "200" ]]; then
    local body
    body="$(head -c 500 "$tmp" | tr '\n' ' ')"
    rm -f "$tmp"
    record_fail "$label" "HTTP ${code}; body=${body}"
    return
  fi

  if ! jq -e '.metadata.prompt_suggestions | (type == "array" and length > 0)' "$tmp" >/dev/null 2>&1; then
    local body
    body="$(head -c 500 "$tmp" | tr '\n' ' ')"
    rm -f "$tmp"
    record_fail "$label" "metadata.prompt_suggestions missing/empty; body=${body}"
    return
  fi

  rm -f "$tmp"
  record_pass "$label"
}

http_post_check() {
  local label="$1"
  local url="$2"
  local payload="$3"
  local must_contain="${4:-schema_version}"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(
    curl -sS --max-time "$TIMEOUT_SECONDS" -o "$tmp" -w '%{http_code}' \
      -X POST "$url" \
      -H 'Content-Type: application/json' \
      --data "$payload" || true
  )"
  local body
  body="$(head -c 320 "$tmp" | tr '\n' ' ')"
  rm -f "$tmp"

  if [[ "$code" != "200" ]]; then
    record_fail "$label" "HTTP ${code}; body=${body}"
    return
  fi
  if [[ -n "$must_contain" ]] && [[ "$body" != *"$must_contain"* ]]; then
    record_fail "$label" "missing '${must_contain}' in body=${body}"
    return
  fi
  record_pass "$label"
}

echo "== Nexo live services smoke =="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Ingest:  ${RUN_INGEST}"
echo

echo "Resolving runtime secrets..."
WEBHOOK_SECRET="$(gcloud secrets versions access latest --secret=WEBHOOK_SECRET --project="$PROJECT_ID")"
OPENCLAW_WEBHOOK_SECRET="$(
  gcloud secrets versions access latest --secret=OPENCLAW_WEBHOOK_SECRET --project="$PROJECT_ID" 2>/dev/null || true
)"

if [[ -z "$WEBHOOK_SECRET" ]]; then
  echo "ERROR: WEBHOOK_SECRET resolved empty"
  exit 1
fi
if [[ -z "$OPENCLAW_WEBHOOK_SECRET" ]]; then
  echo "WARN: OPENCLAW_WEBHOOK_SECRET not found - falling back to WEBHOOK_SECRET for OpenClaw checks"
  OPENCLAW_WEBHOOK_SECRET="$WEBHOOK_SECRET"
fi

echo "Resolving service URLs..."
URL_DEMO_RECEIVER="$(service_url nexo-demo-receiver)"
URL_EXAMPLES_PY="$(service_url nexo-examples-py)"
URL_EXAMPLES_TS="$(service_url nexo-examples-ts)"
URL_MINIMAL_PY="$(service_url nexo-webhook-minimal-py)"
URL_STRUCTURED_PY="$(service_url nexo-webhook-structured-py)"
URL_ADVANCED_PY="$(service_url nexo-webhook-advanced-py)"
URL_MINIMAL_TS="$(service_url nexo-webhook-minimal-ts)"
URL_OPENCLAW_BRIDGE="$(service_url nexo-openclaw-bridge)"
URL_ROUTINES="$(service_url nexo-routines)"
URL_FOOD_ORDERING="$(service_url nexo-food-ordering)"
URL_TRAVEL_PLANNING="$(service_url nexo-travel-planning)"
URL_SKY_DIAMOND="$(service_url luzia-sky-diamond)"
URL_FITNESS_COACH="$(service_url nexo-fitness-coach)"
URL_LANGUAGE_TUTOR="$(service_url nexo-language-tutor)"
URL_NEWS_RAG="$(service_url nexo-news-rag)"
URL_SPORTS_RAG="$(service_url nexo-sports-rag)"
URL_TRAVEL_RAG="$(service_url nexo-travel-rag)"
URL_FOOTBALL_LIVE="$(service_url nexo-football-live)"

echo "== Discovery/health checks =="
http_get_check "demo-receiver health" "${URL_DEMO_RECEIVER}/health" "ok"
http_get_check "examples-py health" "${URL_EXAMPLES_PY}/health" "status"
http_get_check "examples-ts health" "${URL_EXAMPLES_TS}/health" "status"
http_get_check "minimal-py root" "${URL_MINIMAL_PY}/" "webhook-minimal-python"
http_get_check "structured-py root" "${URL_STRUCTURED_PY}/" "schema_version"
http_get_check "advanced-py root" "${URL_ADVANCED_PY}/" "webhook-advanced-python"
http_get_check "minimal-ts root" "${URL_MINIMAL_TS}/" "webhook-minimal-typescript"
http_get_check "openclaw-bridge root" "${URL_OPENCLAW_BRIDGE}/" "webhook-openclaw-bridge-typescript"
http_get_check "routines health" "${URL_ROUTINES}/health" "status"
http_get_check "food-ordering health" "${URL_FOOD_ORDERING}/health" "status"
http_get_check "travel-planning health" "${URL_TRAVEL_PLANNING}/health" "status"
http_get_check "sky-diamond health" "${URL_SKY_DIAMOND}/health" "status"
http_get_check "fitness-coach health" "${URL_FITNESS_COACH}/health" "status"
http_get_check "language-tutor health" "${URL_LANGUAGE_TUTOR}/health" "status"
http_get_check "news-rag health" "${URL_NEWS_RAG}/health" "status"
http_get_check "sports-rag health" "${URL_SPORTS_RAG}/health" "status"
http_get_check "travel-rag health" "${URL_TRAVEL_RAG}/health" "status"
http_get_check "football-live health" "${URL_FOOTBALL_LIVE}/health" "status"

echo
echo "== Functional checks =="

http_post_check \
  "examples-py minimal webhook" \
  "${URL_EXAMPLES_PY}/webhook/minimal" \
  '{"message":{"content":"ping smoke"}}'

http_post_check \
  "examples-ts minimal webhook" \
  "${URL_EXAMPLES_TS}/webhook/minimal" \
  '{"message":{"content":"ping smoke"}}'

http_post_signed_check \
  "minimal-py webhook" \
  "${URL_MINIMAL_PY}/webhook" \
  '{"event":"message_created","message":{"role":"user","content":"hello from smoke"},"profile":{"display_name":"Mark"}}'

http_post_xsignature_check \
  "structured-py webhook" \
  "${URL_STRUCTURED_PY}/" \
  '{"event":"message_created","message":{"role":"user","content":"show me options"},"profile":{"display_name":"Mark"}}'

http_post_xsignature_check \
  "advanced-py webhook" \
  "${URL_ADVANCED_PY}/" \
  '{"event":"message_created","message":{"role":"user","content":"check order"},"context":{"intent":"order_status","order_id":"SMOKE-1"},"profile":{"display_name":"Mark"}}'

http_post_signed_check \
  "minimal-ts webhook" \
  "${URL_MINIMAL_TS}/" \
  '{"event":"message_created","message":{"role":"user","content":"hello from smoke"},"profile":{"display_name":"Mark"}}'

WEBHOOK_SECRET="$OPENCLAW_WEBHOOK_SECRET" http_post_signed_check \
  "openclaw-bridge webhook" \
  "${URL_OPENCLAW_BRIDGE}/webhook" \
  '{"event":"message_created","app":{"id":"smoke-openclaw"},"thread":{"id":"smoke-openclaw-thread"},"message":{"role":"user","content":"say hello from smoke test"},"profile":{"display_name":"Mark"}}' \
  "provider"

http_post_signed_prompt_suggestions_check \
  "routines webhook" \
  "${URL_ROUTINES}/" \
  '{"event":"message_created","message":{"role":"user","content":"morning briefing"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "food-ordering webhook" \
  "${URL_FOOD_ORDERING}/" \
  '{"event":"message_created","message":{"role":"user","content":"show vegan options"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "travel-planning webhook" \
  "${URL_TRAVEL_PLANNING}/" \
  '{"event":"message_created","message":{"role":"user","content":"plan 3 days in Lisbon"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "sky-diamond webhook" \
  "${URL_SKY_DIAMOND}/webhook" \
  '{"event":"message_created","thread":{"id":"smoke-sky-diamond"},"message":{"role":"user","content":"Sky Diamond"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "fitness-coach webhook" \
  "${URL_FITNESS_COACH}/" \
  '{"event":"message_created","message":{"role":"user","content":"design a beginner workout plan"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "language-tutor webhook" \
  "${URL_LANGUAGE_TUTOR}/" \
  '{"event":"message_created","message":{"role":"user","content":"teach me how to order food in Italian"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "news-rag webhook" \
  "${URL_NEWS_RAG}/" \
  '{"event":"message_created","message":{"role":"user","content":"top world headlines now"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "sports-rag webhook" \
  "${URL_SPORTS_RAG}/" \
  '{"event":"message_created","message":{"role":"user","content":"important football results"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "travel-rag webhook" \
  "${URL_TRAVEL_RAG}/" \
  '{"event":"message_created","message":{"role":"user","content":"suggest a city break"},"profile":{"display_name":"Mark"}}'

http_post_signed_prompt_suggestions_check \
  "football-live webhook" \
  "${URL_FOOTBALL_LIVE}/" \
  '{"event":"message_created","message":{"role":"user","content":"who are top scorers"},"profile":{"display_name":"Mark"}}'

http_get_check "demo-receiver events endpoint" "${URL_DEMO_RECEIVER}/v1/events/smoke-demo" "events"
http_get_expect_code_check "demo-receiver ingest endpoint (method check)" "${URL_DEMO_RECEIVER}/v1/ingest/smoke-demo" "405" "Method Not Allowed"

if [[ "${RUN_INGEST}" == "true" ]]; then
  echo
  echo "== RAG ingest checks =="
  http_post_signed_check \
    "news-rag ingest trigger" \
    "${URL_NEWS_RAG}/ingest" \
    '{}' \
    "ingest"
  http_post_signed_check \
    "sports-rag live ingest trigger" \
    "${URL_SPORTS_RAG}/ingest/live" \
    '{}' \
    "summary"
  http_post_signed_check \
    "travel-rag ingest trigger" \
    "${URL_TRAVEL_RAG}/ingest" \
    '{}' \
    "summary"
  http_post_signed_check \
    "football-live ingest trigger" \
    "${URL_FOOTBALL_LIVE}/ingest/live" \
    '{}' \
    "matches_updated"
fi

echo
echo "== Summary =="
echo "Passed: ${PASS_COUNT}"
echo "Failed: ${FAIL_COUNT}"

if (( FAIL_COUNT > 0 )); then
  echo
  echo "Failures:"
  for failure in "${FAILURES[@]}"; do
    echo " - ${failure}"
  done
  exit 1
fi

echo "All live smoke checks passed."
