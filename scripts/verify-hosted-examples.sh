#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-luzia-nexo-api-examples}"
REGION="${REGION:-europe-west1}"
PY_SERVICE_NAME="${PY_SERVICE_NAME:-nexo-examples-py}"
TS_SERVICE_NAME="${TS_SERVICE_NAME:-nexo-examples-ts}"
SHARED_SECRET="${EXAMPLES_SHARED_API_SECRET:-}"

py_url="$(gcloud run services describe "${PY_SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ts_url="$(gcloud run services describe "${TS_SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"

echo "Python service: ${py_url}"
echo "TypeScript service: ${ts_url}"

echo "== Health checks =="
curl -fsS "${py_url}/health" >/dev/null
curl -fsS "${ts_url}/health" >/dev/null

echo "== Auth checks =="
if [[ -n "${SHARED_SECRET}" ]]; then
  curl -fsS -X POST "${py_url}/webhook/minimal" \
    -H "Content-Type: application/json" \
    -H "X-App-Secret: ${SHARED_SECRET}" \
    -d '{"message":{"content":"ping"}}' >/dev/null

  curl -fsS -X POST "${ts_url}/webhook/minimal" \
    -H "Content-Type: application/json" \
    -H "X-App-Secret: ${SHARED_SECRET}" \
    -d '{"message":{"content":"ping"}}' >/dev/null
else
  curl -fsS -X POST "${py_url}/webhook/minimal" \
    -H "Content-Type: application/json" \
    -d '{"message":{"content":"ping"}}' >/dev/null

  curl -fsS -X POST "${ts_url}/webhook/minimal" \
    -H "Content-Type: application/json" \
    -d '{"message":{"content":"ping"}}' >/dev/null
fi

echo "Hosted examples verification passed"
