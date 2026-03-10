# Luzia Nexo Partner Integration APIs

Nexo provides a managed Agent Runtime with consented profile context and reliable webhook delivery.
Nexo handles runtime orchestration. Your partner service focuses on domain logic.

Build partner experiences on top of Nexo with:

- Signed webhook delivery
- Consented profile context
- Rich cards and actions
- Streaming responses
- Proactive push events

## Start Here

1. [Quickstart](quickstart.md) - get a webhook running.
2. [Demo Catalog](demos.md) - browse all demos and live services.
3. [Examples Deep Dive](examples-showcase.md) - inspect full RAG and response patterns.
4. [API Reference](partner-api-reference.md) - integrate contract details.
5. [Hosting](hosting.md) - deploy every server-side demo to Cloud Run.

## Integration Architecture

```mermaid
sequenceDiagram
    autonumber
    participant User as End User
    participant Luzia as Luzia Backend
    participant Nexo as Nexo Runtime
    participant Partner as Partner Service

    User->>Luzia: Send message
    Luzia->>Nexo: Delegate partner handling
    Nexo->>Partner: Signed webhook request
    Partner->>Partner: Verify signature + process domain logic
    alt JSON mode
        Partner-->>Nexo: Response envelope with text/cards/actions
    else SSE mode
        Partner-->>Nexo: Stream delta/done events
    end
    Nexo-->>Luzia: Runtime-processed result
    Luzia-->>User: Final reply
```

## Capability Surface

| Capability | What it means in practice | Example |
|---|---|---|
| Webhook contract | Deterministic request and response schema | `webhook/minimal` |
| Rich UI payloads | Cards, actions, structured metadata | `webhook/structured` |
| Operational hardening | Signature checks, retries, idempotency | `webhook/advanced` |
| Retrieval-augmented responses | Domain retrieval + LLM + citations | `news-rag`, `sports-rag`, `travel-rag`, `football-live` |
| OpenClaw integration | Bridge from Nexo webhook to OpenClaw responses API | `openclaw-bridge` |
| Proactive delivery | Partner-pushed events into subscriber threads | `partner-api/proactive` |

## Live Examples

| Service | URL |
|---|---|
| nexo-news-rag | <https://nexo-news-rag-v3me5awkta-ew.a.run.app/> |
| nexo-sports-rag | <https://nexo-sports-rag-v3me5awkta-ew.a.run.app/> |
| nexo-travel-rag | <https://nexo-travel-rag-v3me5awkta-ew.a.run.app/> |
| nexo-football-live | <https://nexo-football-live-v3me5awkta-ew.a.run.app/> |
| nexo-openclaw-bridge | <https://nexo-openclaw-bridge-v3me5awkta-ew.a.run.app/> |
| nexo-examples-py | <https://nexo-examples-py-v3me5awkta-ew.a.run.app/> |
| nexo-examples-ts | <https://nexo-examples-ts-v3me5awkta-ew.a.run.app/> |
| nexo-demo-receiver | <https://nexo-demo-receiver-v3me5awkta-ew.a.run.app/> |

For source links and what each demo does, use [Demo Catalog](demos.md).

## Design Principles

- Contract-first: same schema rules across local and production.
- Capability-first: docs describe what can be built, not only minimal setup.
- Deployable-by-default: all server demos are deployment-ready.
- Safe configuration: no secrets hardcoded in code or docs.
