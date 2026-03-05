# Luzia Nexo

Luzia Partner Integration APIs.

Integrate your backend with Luzia through Nexo using webhooks and APIs. Nexo provides a clean thread-based interface, consented user profile context, and managed webhook delivery so you can focus on agent logic and response quality.

It's really that simple.

## Webhook flow (integration architecture)

```mermaid
sequenceDiagram
    autonumber
    participant User as End User
    participant Luzia as Luzia Backend
    participant Nexo as Nexo Agent Runtime
    participant Partner as Partner Webhook

    User->>Luzia: Send message
    Luzia->>Nexo: Delegate partner connection handling
    Luzia->>Luzia: Pre-process user input (for example language translation)
    Nexo->>Nexo: Pre-process runtime context (including translation when needed)
    Nexo->>Partner: POST webhook request (signed + consented profile context)
    Partner->>Partner: Verify secret + signature
    Partner->>Partner: Process profile context for personalization and decisions
    alt Traditional response
        Partner-->>Nexo: 200 JSON (schema_version + status + content_parts/cards/actions)
    else Streaming response
        Partner-->>Nexo: 200 text/event-stream (SSE)
    end
    Nexo-->>Luzia: Return partner result
    Luzia->>Luzia: Post-process webhook output (for example language translation)
    Luzia-->>User: Return assistant reply
```

## Start in 3 steps

1. Get your app secret at [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
2. Implement your webhook using [Quickstart](quickstart.md)
3. Activate your webhook in Nexo by configuring your webhook URL and app secret in the partner portal

Use [API Reference](partner-api-reference.md) for payload, signature, and response contract details.

Note: the app secret is required to receive real traffic from Nexo. For local/offline development, you can run and test the example webhook servers directly without creating a partner app first.

## Live examples

Hosted reference services you can test before building your own:

| Language | Live service | Source code |
|----------|-------------|-------------|
| Python | [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/) | [examples/hosted/python](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/python) |
| TypeScript | [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/) | [examples/hosted/typescript](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/hosted/typescript) |

For standalone webhook snippets see [examples/webhook](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook).

If you are connecting through OpenClaw, use the OpenClaw Bridge example:
- [examples/webhook/openclaw-bridge](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/openclaw-bridge)

## Profile context

- Webhook payloads include consented profile attributes such as:
  - `locale`
  - `language`
  - `location` (for example city/country)
  - `age` or age range
  - `date_of_birth`
  - `gender`
  - `dietary_preferences`
  - `preferences` and selected profile facts
- Availability depends on app permissions and user consent.
- Additional attributes are added over time while keeping backward compatibility.
- Parse defensively and ignore unknown fields.

## Optional deployment examples

- Docker and Cloud Run examples: [Hosting (Optional)](hosting.md)

## Support

- [mmm@luzia.com](mailto:mmm@luzia.com)
