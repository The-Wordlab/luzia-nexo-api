# A2A Conformance Matrix

Status: rollout tracker
Updated: 2026-03-12

Use this matrix to keep every example on the same A2A profile.

| Example | Agent card | Sync envelope | Stream lifecycle | Artifact-only completion | Failed task -> error | Notes |
|---|---|---|---|---|---|---|
| news-rag | complete | complete | complete | complete | complete | baseline implemented + tests passing |
| sports-rag | complete | complete | complete | complete | complete | aligned to shared A2A envelope + stream events |
| travel-rag | complete | complete | complete | complete | complete | aligned to shared A2A envelope + stream events |
| fitness-coach | complete | complete | complete | complete | complete | aligned to shared A2A envelope + stream events |
| travel-planner | complete | complete | complete | complete | complete | aligned to shared A2A envelope + stream events |
| language-tutor | complete | complete | complete | complete | complete | aligned to shared A2A envelope + stream events |
| routines | complete | complete | complete | complete | complete | aligned with shared A2A envelope + stream events |
| food-ordering | complete | complete | complete | complete | complete | aligned with shared A2A envelope + stream events |
| travel-planning | complete | complete | complete | complete | complete | aligned with shared A2A envelope + stream events |
| football-live | complete | complete | complete | complete | complete | aligned with shared A2A envelope + stream events |
| chain-demo | n/a | n/a | n/a | n/a | n/a | simulator-only demo app, not a webhook example |

## Shared checks

1. `/.well-known/agent.json` publishes valid capability metadata.
2. Sync webhook response validates against canonical envelope.
3. Stream events terminate with valid lifecycle semantics.
4. Artifact-only completed response is accepted.
5. Failed task lifecycle resolves to error semantics.
