# Luzia Nexo API

Reference implementation for Nexo partner integrations.

Use this repository to:
- build and test webhook handlers (Python or TypeScript)
- send proactive Partner API requests
- reference optional deployment examples (Docker, Cloud Run)

## Links

- API Documentation: [the-wordlab.github.io/luzia-nexo-api](https://the-wordlab.github.io/luzia-nexo-api/)
- Luzia Nexo: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)

## Webhook flow (target architecture)

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
    Nexo->>Partner: POST webhook request (signed)
    Partner->>Partner: Verify secret + signature
    alt Traditional response
        Partner-->>Nexo: 200 JSON (text/reply)
    else Streaming response
        Partner-->>Nexo: 200 text/event-stream (SSE)
    end
    Nexo-->>Luzia: Return partner result
    Luzia->>Luzia: Post-process webhook output (for example language translation)
    Luzia-->>User: Return assistant reply
```

## Quick start

1. Implement your webhook endpoint in your backend.
2. Configure your webhook URL and app secret at [nexo.luzia.com/partners](https://nexo.luzia.com/partners).
3. Test your webhook response shape locally:

```json
{
  "text": "Your assistant response"
}
```

4. Verify request signature handling (`X-Timestamp`, `X-Signature`) using the contract in [API Reference](docs/partner-api-reference.md).

Read the full integration guide: [API Documentation](https://the-wordlab.github.io/luzia-nexo-api/)

## Repository map

- [`examples/`](examples/) - local webhook and partner API examples
- [`examples-hosted/`](examples-hosted/) - Cloud Run deployable example services
- [`infra/terraform/`](infra/terraform/) - GCP infrastructure
- [`docs/`](docs/) - documentation source for the published docs site

## Maintainer commands

```bash
make check-toolchain
make test-all
make docs-build
```

## Support

- [mmm@luzia.com](mailto:mmm@luzia.com)
