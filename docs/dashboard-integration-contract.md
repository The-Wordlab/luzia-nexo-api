# Dashboard Integration Contract

This contract defines how `luzia-nexo` dashboard surfaces demo receiver events.

## Design choice

Dashboard should not call demo receiver directly with raw demo secrets.
Use `luzia-nexo` backend as proxy boundary.

## Backend proxy endpoints (in luzia-nexo)

1. `POST /api/demo-receiver/apps/{app_id}/ingest`
2. `GET /api/demo-receiver/apps/{app_id}/events?limit=20`

Backend responsibilities:

- Authenticate dashboard user
- Authorize app/org access
- Resolve demo key from app configuration
- Call demo receiver service
- Return sanitized payloads only

## Demo receiver endpoints

1. `POST /v1/ingest/{demo_key}`
2. `GET /v1/events/{demo_key}?limit=20`

## Event payload contract

Stored event fields:

- `event_id` (string)
- `received_at` (unix epoch seconds)
- `payload` (object, secret-redacted)

## Guardrails

- Secret-like keys (`*token*`, `*secret*`, `*authorization*`) redacted
- TTL expiration and max events per key
- Demo key format validation

## Non-goals

- Long-term analytics storage
- Production-grade durable event pipelines
- Cross-region replication
