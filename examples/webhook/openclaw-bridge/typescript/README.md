# OpenClaw Bridge Webhook - TypeScript/Node

Nexo-compatible webhook implementation that forwards user requests to OpenClaw Gateway.

## What it does

1. Receives Nexo webhook payloads at `POST /webhook`
2. Verifies signature (`X-Timestamp`, `X-Signature`) when `WEBHOOK_SECRET` is set
3. Calls OpenClaw `POST /v1/responses`
4. Returns canonical Nexo rich response envelope (JSON mode) or Nexo SSE (`delta`/`done`) in stream mode

## Streaming support

This bridge supports streaming in two ways:

- Request header: `Accept: text/event-stream`
- Payload flag: `stream: true` (or `metadata.stream: true`)

When streaming is enabled, the bridge maps OpenClaw response stream events into:

```text
data: {"type":"delta","text":"..."}

data: {"type":"done"}
```

## Environment

- `OPENCLAW_GATEWAY_TOKEN` (required)
- `OPENCLAW_BASE_URL` (default: `http://127.0.0.1:18789`)
- `OPENCLAW_AGENT_ID` (default: `main`)
- `WEBHOOK_SECRET` (optional, but recommended)
- `BRIDGE_ACCESS_KEY` (recommended in hosted environments; requires `X-Bridge-Key` header on requests)
- `ALLOW_REQUEST_SESSION_KEY` (default: `false`; when `true`, accepts `X-OpenClaw-Session-Key` or `metadata.openclaw_session_key`)
- `ALLOW_REQUEST_OPENCLAW_TOKEN` (default: `false`; when `true`, accepts `X-OpenClaw-Gateway-Token` if server token is unset)
- `OPENCLAW_ORIGIN_HEADER_NAME` (default: `X-Nexo-Bridge-Key`; optional extra header sent from bridge to OpenClaw)
- `OPENCLAW_ORIGIN_HEADER_VALUE` (value for `OPENCLAW_ORIGIN_HEADER_NAME`; use this for server-side origin allowlisting)
- `PORT` (default: `8082`)

Use `.env.example` as the template and keep real values only in local `.env` (ignored by git).

If your OpenClaw endpoint is exposed via Caddy under a path prefix (current production shape), include the prefix in `OPENCLAW_BASE_URL`:

- `OPENCLAW_BASE_URL=https://nexo-1.luzia.com/openclaw`

## Run

```bash
cd examples/webhook/openclaw-bridge/typescript
cp .env.example .env
# edit .env with your values
set -a; source .env; set +a
node openclaw-bridge-server.mjs
```

## Test

```bash
cd examples/webhook/openclaw-bridge/typescript
node --test test-openclaw-bridge-server.mjs
```

## Local curl (JSON mode)

```bash
curl -X POST "http://localhost:8082/webhook" \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Key: your_bridge_access_key" \
  -d '{
    "event":"message_received",
    "app":{"id":"app-1","name":"Demo"},
    "thread":{"id":"thread-1","customer_id":"cust-1"},
    "message":{"id":"msg-1","seq":1,"role":"user","content":"hello","content_json":{}},
    "history_tail":[],
    "timestamp":"2026-03-04T12:00:00Z"
  }'
```

## Local curl (streaming mode)

```bash
curl -N -X POST "http://localhost:8082/webhook" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "X-Bridge-Key: your_bridge_access_key" \
  -H "X-OpenClaw-Session-Key: demo:frontend-session-123" \
  -d '{
    "event":"message_received",
    "app":{"id":"app-1","name":"Demo"},
    "thread":{"id":"thread-1","customer_id":"cust-1"},
    "message":{"id":"msg-1","seq":1,"role":"user","content":"hello","content_json":{}},
    "history_tail":[],
    "timestamp":"2026-03-04T12:00:00Z"
  }'
```

## Notes

- Session mapping uses: `x-openclaw-session-key = nexo:thread:<thread.id>`
- If `ALLOW_REQUEST_SESSION_KEY=true`, frontend/demo can override with `X-OpenClaw-Session-Key`.
- OpenClaw stream events are normalized to Nexo `delta`/`done` format.
- Prefer `BRIDGE_ACCESS_KEY` + server-side `OPENCLAW_GATEWAY_TOKEN` instead of sending the OpenClaw token from frontend.
- For OpenClaw endpoint hardening, set a shared secret via `OPENCLAW_ORIGIN_HEADER_VALUE` and enforce it in your reverse proxy for `/openclaw/v1/responses`.
- In production, keep these values aligned: bridge `OPENCLAW_GATEWAY_TOKEN`, OpenClaw `gateway.auth.token` (or its env fallback), and reverse-proxy `X-Nexo-Bridge-Key` secret.

## Direct endpoint verification (outside bridge)

Use this to verify OpenClaw is reachable before debugging the bridge:

```bash
BASE='https://nexo-1.luzia.com/openclaw/v1/responses'
KEY=$(ssh root@46.225.88.64 "grep '^NEXO_BRIDGE_ORIGIN_KEY=' /root/openclaw/.env | cut -d= -f2-")
TOK=$(ssh root@46.225.88.64 "grep '^OPENCLAW_GATEWAY_TOKEN=' /root/openclaw/.env | cut -d= -f2-")

curl -sS -X POST "$BASE" \
  -H 'Content-Type: application/json' \
  -H "X-Nexo-Bridge-Key: $KEY" \
  -H "Authorization: Bearer $TOK" \
  -H 'x-openclaw-agent-id: main' \
  -H 'x-openclaw-session-key: nexo:test' \
  --data '{"model":"openclaw:main","input":"ping","stream":false}'
```

Expected result:
- `200` with OpenClaw response payload.

Common pitfall:
- Auth can be correct but payload still returns `400` if `input` shape is invalid.
  For smoke tests, use a string input (`"input":"ping"`).
