# Demo Catalog

This page is the fastest way to see what teams can launch with Nexo today.

Think of these demos as reusable growth accelerators:
- proven integration patterns you can clone
- live examples you can validate immediately
- starter architectures you can adapt to your own domain

All **server-side** demos are deployable to Cloud Run.
The only examples that are not deployed as services are CLI scripts under `examples/partner-api/proactive`.

All webhook demos now expose a clean `GET /` service-discovery response so teams can inspect:
- service purpose
- supported routes
- auth expectations
- schema version

## Why there are two demo families

The folder split is by **contract type**, not by local-vs-production:

- `examples/webhook/*`: services that receive Nexo webhook events and return Nexo response envelopes.
- `examples/hosted/*`: reference HTTP APIs used for capability demos and contract testing.

Both are deployable and production-oriented.

## Live deployed demos

| Demo | Contract | Capability | Live URL | Source |
|---|---|---|---|---|
| News Feed RAG | Webhook | RSS ingestion + retrieval + source cards | [nexo-news-rag](https://nexo-news-rag-v3me5awkta-ew.a.run.app/) | [news-rag/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/news-rag/python) |
| Sports Feed RAG | Webhook | Scores, standings, news routing + event detection | [nexo-sports-rag](https://nexo-sports-rag-v3me5awkta-ew.a.run.app/) | [sports-rag/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/sports-rag/python) |
| Travel RAG | Webhook | Destination and itinerary retrieval | [nexo-travel-rag](https://nexo-travel-rag-v3me5awkta-ew.a.run.app/) | [travel-rag/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/travel-rag/python) |
| Football Live RAG | Webhook | Football deep-dive: live matches, standings, top scorers | [nexo-football-live](https://nexo-football-live-v3me5awkta-ew.a.run.app/) | [football-live/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/football-live/python) |
| Daily Routines | Webhook | Morning briefings, schedule actions, follow-up nudges | [nexo-routines](https://nexo-routines-367427598362.europe-west1.run.app/) | [routines/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/routines/python) |
| Food Ordering | Webhook | Food-commerce flagship: discovery, basket, checkout, tracking, reorder | [nexo-food-ordering](https://nexo-food-ordering-367427598362.europe-west1.run.app/) | [food-ordering/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/food-ordering/python) |
| Travel Planning | Webhook | Travel flagship: itinerary, flights, booking handoff, budget, disruption | [nexo-travel-planning](https://nexo-travel-planning-367427598362.europe-west1.run.app/) | [travel-planning/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/travel-planning/python) |
| Fitness Coach | Webhook | Workout plans, progress checks, nutrition guidance | [nexo-fitness-coach](https://nexo-fitness-coach-367427598362.europe-west1.run.app/) | [fitness-coach/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/fitness-coach/python) |
| Travel Planner | Webhook | Secondary compatibility travel slice: flights and booking handoff | [nexo-travel-planner](https://nexo-travel-planner-367427598362.europe-west1.run.app/) | [travel-planner/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/travel-planner/python) |
| Language Tutor | Webhook | Phrase coaching, quick quizzes, lesson plans | [nexo-language-tutor](https://nexo-language-tutor-367427598362.europe-west1.run.app/) | [language-tutor/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/language-tutor/python) |
| OpenClaw Bridge | Webhook | Nexo webhook to OpenClaw `/v1/responses` adapter | [nexo-openclaw-bridge](https://nexo-openclaw-bridge-v3me5awkta-ew.a.run.app/) | [openclaw-bridge/typescript](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/openclaw-bridge/typescript) |
| Hosted Python API | Reference API | Minimal authenticated reference API | [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/) | [hosted/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/python) |
| Hosted TypeScript API | Reference API | Minimal authenticated reference API | [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/) | [hosted/typescript](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/typescript) |
| Demo Receiver | Reference API | Webhook contract receiver for smoke and drift checks | [nexo-demo-receiver](https://nexo-demo-receiver-v3me5awkta-ew.a.run.app/) | [hosted/demo-receiver](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/demo-receiver) |

## Webhook examples you can run and deploy

| Example | Language | What it demonstrates |
|---|---|---|
| `webhook/minimal` | Python + TypeScript | Smallest valid webhook implementation |
| `webhook/structured` | Python | Rich card/action response envelope |
| `webhook/advanced` | Python | Connector behavior, retries, idempotency |
| `webhook/openclaw-bridge` | TypeScript | OpenClaw integration with signed webhook verification |
| `webhook/news-rag` | Python | Feed ingestion + retrieval + citations |
| `webhook/sports-rag` | Python | Multi-source sports retrieval + intent routing |
| `webhook/travel-rag` | Python | Destination knowledge + travel advice |
| `webhook/football-live` | Python | Live football domain with structured cards |
| `webhook/routines` | Python | Morning briefings, schedule actions, and follow-up nudges |
| `webhook/food-ordering` | Python | Menu search, order composition, and checkout flow |
| `webhook/travel-planning` | Python | Multi-step itinerary, budget, and disruption replanning |
| `webhook/fitness-coach` | Python | Workout plans, progress snapshots, and nutrition guidance |
| `webhook/travel-planner` | Python | Conversational trip planning with booking handoff cards |
| `webhook/language-tutor` | Python | Language phrase help, quizzes, and lesson plans |

## Partner API proactive scripts (CLI, not service deployments)

These are tooling examples for pushing events through the Partner API:

| Example | Languages | Purpose |
|---|---|---|
| `partner-api/proactive` | Bash, Python, TypeScript | Demonstrates partner-initiated event delivery and auth |

## Suggested reading path

1. [Quickstart](quickstart.md) - implement your first webhook in minutes.
2. [Demo Catalog](demos.md) - pick the capability pattern you want.
3. [Examples Deep Dive](examples-showcase.md) - inspect architecture and payloads.
4. [Hosting](hosting.md) - deploy to Cloud Run.
5. [API Reference](partner-api-reference.md) - wire production integration details.
