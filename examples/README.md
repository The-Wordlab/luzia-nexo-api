# Examples

Runnable Nexo integration examples.

## Current public inventory

- `webhook/minimal` - smallest valid webhook example in Python and TypeScript
- `webhook/structured` - richer envelope example with cards and locale-aware hints
- `webhook/advanced` - idempotency, retries, and action-routing webhook example
- `webhook/food-ordering` - flagship multi-step commerce webhook example
- `webhook/openclaw-bridge` - adapter between Nexo webhooks and OpenClaw `/v1/responses`
- `partner-api/proactive` - partner-initiated event delivery examples
- `hosted/python` - hosted reference API for Python consumers
- `hosted/typescript` - hosted reference API for TypeScript consumers
- `identity-bridge` - partner-owned login and identity-linking reference flow that hands off into Nexo-hosted `/apps/{slug}/auth`, `/apps/{slug}/profile`, and `/apps/{slug}/onboarding`

This repository does not own first-party app shells. Public lightweight app
consumers, when needed, should stay thin and sit on top of the mirrored SDK,
not replace the webhook/reference examples. Keep that mirror current with:

```bash
./scripts/sync-nexo-sdk.sh
```

## Docker Compose quickstart

Run all webhook examples with one command:

```bash
cd examples/
cp .env.example .env      # fill in API keys as needed
docker compose up --build
```

### Port reference

| Service        | Host port | Endpoint        | Language | Description                                  |
|----------------|-----------|-----------------|----------|----------------------------------------------|
| minimal        | 8080      | POST /webhook   | Python   | Echo server, minimal webhook contract         |
| structured     | 8081      | POST /          | Python   | Locale-aware greetings, card hints            |
| advanced       | 8082      | POST /          | Python   | Connector actions, idempotency, retry         |

### Quick smoke test

```bash
# minimal
curl -s -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"message": {"content": "hello"}}' | jq .
```

### Pointing Nexo at local services

Set webhook URLs in the Nexo dashboard to `http://host.docker.internal:<port>/<path>`
(or your machine's LAN IP if Nexo runs in Docker on the same host).

### Stopping

```bash
docker compose down       # stop containers, keep volumes
docker compose down -v    # stop containers and delete local data volumes
```

Includes an explicit **OpenClaw Bridge** example at `webhook/openclaw-bridge` for teams that want a webhook adapter between Nexo payloads and OpenClaw `/v1/responses`.

Profile context note:
- Webhook payloads include consented profile context (for example `locale`, `language`, `location`, `age`, `date_of_birth`, `gender`, `dietary_preferences`, and preferences/facts).
- Additional attributes are added over time while keeping backward compatibility.
- Build examples and integrations to safely ignore unknown fields.

Folders:
- `webhook/minimal`
- `webhook/structured`
- `webhook/advanced`
- `webhook/openclaw-bridge`
- `webhook/food-ordering`
- `partner-api/proactive`
- `hosted/python`
- `hosted/typescript`
- `identity-bridge`

Run all example tests from the repo root:

```bash
make test-examples
```
