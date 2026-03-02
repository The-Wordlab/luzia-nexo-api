# Demo Receiver Design

## Purpose

Provide stable hosted webhook URLs for demos while remaining isolated from production systems.

## Minimal-safe behavior

1. Accept events at `POST /v1/ingest/{demo_key}`.
2. Store recent events per `demo_key`.
3. Return events through `GET /v1/events/{demo_key}`.
4. Redact obvious secret/token fields.
5. Enforce retention bounds via TTL and max events per key.

## Next storage step

Current sprint uses in-memory storage for bootstrap.
A follow-up slice can switch to Firestore backend with the same API contract.
