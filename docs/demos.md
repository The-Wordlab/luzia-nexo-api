# Demo Catalog

See what you can build with Nexo. Every example below is a production-ready Connected App or reference-service pattern you can clone, customize, and deploy.

- **Clone** any example and run it locally
- **Test** against live deployed instances immediately
- **Deploy** to Cloud Run with a single command

All webhook demos expose a `GET /` service-discovery endpoint with service info, supported routes, auth expectations, and schema version.

## Webhook vs. hosted examples

The folder split is by **contract type**:

- `examples/webhook/*` -- services that receive Nexo webhook events and return response envelopes.
- `examples/hosted/*` -- reference HTTP APIs for capability demos and contract testing.

Both are deployable and production-ready.

## Live deployed demos

| Demo | Contract | Capability | Live URL | Source |
|---|---|---|---|---|
| Food Ordering | Webhook | Discovery, basket, checkout, tracking, reorder | [nexo-food-ordering](https://nexo-food-ordering-v3me5awkta-ew.a.run.app/) | [food-ordering/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/food-ordering/python) |
| OpenClaw Bridge | Webhook | Nexo webhook to OpenClaw `/v1/responses` adapter | [nexo-openclaw-bridge](https://nexo-openclaw-bridge-v3me5awkta-ew.a.run.app/) | [openclaw-bridge/typescript](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/openclaw-bridge/typescript) |
| Hosted Python API | Reference API | Minimal authenticated reference API | [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/) | [hosted/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/python) |
| Hosted TypeScript API | Reference API | Minimal authenticated reference API | [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/) | [hosted/typescript](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/typescript) |
| Demo Receiver | Reference API | Webhook contract receiver for smoke testing | [nexo-demo-receiver](https://nexo-demo-receiver-v3me5awkta-ew.a.run.app/) | [hosted/demo-receiver](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/demo-receiver) |

## Webhook examples

| Example | Language | What it demonstrates |
|---|---|---|
| `webhook/minimal` | Python + TypeScript | Smallest valid webhook implementation |
| `webhook/structured` | Python | Rich card/action response envelope |
| `webhook/advanced` | Python | Signature verification, retries, idempotency |
| `webhook/openclaw-bridge` | TypeScript | OpenClaw integration with signed webhook verification |
| `webhook/food-ordering` | Python | Menu search, order composition, and checkout flow |

## Partner API proactive scripts

CLI tooling for pushing events through the Partner API:

| Example | Languages | Purpose |
|---|---|---|
| `partner-api/proactive` | Bash, Python, TypeScript | Partner-initiated event delivery and auth |

## Suggested reading path

1. [Quickstart](quickstart.md) -- implement your first webhook in minutes.
2. [Demo Catalog](demos.md) -- pick the capability pattern you want.
3. [Examples Deep Dive](examples-showcase.md) -- inspect architecture and payloads.
4. [Hosting](hosting.md) -- deploy to Cloud Run.
5. [Partner API Reference](partner-api-reference.md) -- full contract details.
