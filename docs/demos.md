# Demo Catalog

See what you can build with Nexo. Every example below is a production-ready integration pattern you can clone, customize, and deploy.

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
| News Feed RAG | Webhook | RSS ingestion + retrieval + source cards | [nexo-news-rag](https://nexo-news-rag-v3me5awkta-ew.a.run.app/) | [news-rag/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/news-rag/python) |
| Sports Feed RAG | Webhook | Scores, standings, news routing + event detection | [nexo-sports-rag](https://nexo-sports-rag-v3me5awkta-ew.a.run.app/) | [sports-rag/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/sports-rag/python) |
| Travel RAG | Webhook | Destination and itinerary retrieval | [nexo-travel-rag](https://nexo-travel-rag-v3me5awkta-ew.a.run.app/) | [travel-rag/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/travel-rag/python) |
| Football Live RAG | Webhook | Live matches, standings, top scorers | [nexo-football-live](https://nexo-football-live-v3me5awkta-ew.a.run.app/) | [football-live/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/football-live/python) |
| Daily Routines | Webhook | Morning briefings, schedule actions, follow-up nudges | [nexo-routines](https://nexo-routines-v3me5awkta-ew.a.run.app/) | [routines/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/routines/python) |
| Food Ordering | Webhook | Discovery, basket, checkout, tracking, reorder | [nexo-food-ordering](https://nexo-food-ordering-v3me5awkta-ew.a.run.app/) | [food-ordering/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/food-ordering/python) |
| Travel Planning | Webhook | Itinerary, flights, booking handoff, budget, disruption handling | [nexo-travel-planning](https://nexo-travel-planning-v3me5awkta-ew.a.run.app/) | [travel-planning/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/travel-planning/python) |
| Sky Diamond | Webhook | Stateful detective game with rich cards, prompt suggestions, JSON, and SSE | [luzia-sky-diamond](https://luzia-sky-diamond-v3me5awkta-ew.a.run.app/) | [detective-game/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/detective-game/python) |
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
| `webhook/news-rag` | Python | Feed ingestion + retrieval + citations |
| `webhook/sports-rag` | Python | Multi-source sports retrieval + intent routing |
| `webhook/travel-rag` | Python | Destination knowledge + travel advice |
| `webhook/football-live` | Python | Live football domain with structured cards |
| `webhook/routines` | Python | Morning briefings, schedule actions, and follow-up nudges |
| `webhook/food-ordering` | Python | Menu search, order composition, and checkout flow |
| `webhook/travel-planning` | Python | Multi-step itinerary, budget, and disruption replanning |
| `webhook/detective-game` | Python | Stateful game runtime with pinned thread progress, cards, and SSE |

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
5. [API Reference](partner-api-reference.md) -- full contract details.
