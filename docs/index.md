# Luzia Nexo API Docs

Fast partner integration docs.

## Integration at a glance

```mermaid
sequenceDiagram
    autonumber
    participant User as End User
    participant Nexo as Nexo Thread Runtime
    participant Partner as Partner Webhook

    User->>Nexo: Sends message in a thread
    Nexo->>Nexo: Resolve thread, character, and tools
    Nexo->>Partner: POST webhook request with app headers and signature
    Partner->>Partner: Verify secret and signature
    alt Traditional response
        Partner-->>Nexo: 200 JSON with text/reply
    else Streaming response
        Partner-->>Nexo: 200 text/event-stream (SSE chunks + done)
    end
    Nexo-->>User: Assistant reply in the same thread
    Note over Nexo,Partner: Transient failures are retried by Nexo.
```

## Start here

1. **Onboarding (5 minutes)**: [Onboarding](onboarding.md)
2. **Quickstart (hosted or self-deploy)**: [Quickstart](quickstart.md)
3. **Code examples**: [Examples](examples.md)

## Live hosted services

- Demo receiver: [nexo-demo-receiver](https://nexo-demo-receiver-v3me5awkta-ew.a.run.app)
- Hosted Python examples: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app)
- Hosted TypeScript examples: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app)

## API secret and support

- Partner portal: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com) (Mark MacMahon)

## What these docs cover

- How to use hosted examples immediately
- How to deploy your own copy on GCP
- Direct links to Python, TypeScript, and cURL examples

## Source repository

- [github.com/The-Wordlab/luzia-nexo-api](https://github.com/The-Wordlab/luzia-nexo-api)
