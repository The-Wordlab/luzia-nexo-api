# Partner API Reference

Base URL:
- `https://nexo.luzia.com/api`

Authentication headers:
- `X-App-Id: <app_uuid>`
- `X-App-Secret: <app_secret>`

## Core endpoints

- `GET /apps/{app_id}/subscribers`
- `GET /apps/{app_id}/subscribers/{subscriber_id}/threads`
- `GET /apps/{app_id}/threads`
- `GET /apps/{app_id}/threads/{thread_id}/messages`
- `POST /apps/{app_id}/threads`
- `POST /apps/{app_id}/threads/{thread_id}/messages`
- `POST /apps/{app_id}/threads/{thread_id}/messages/assistant`

## Webhook request (Nexo -> your endpoint)

Headers:
- `Content-Type: application/json`
- `X-App-Id: <app_uuid>`
- `X-Timestamp: <unix_seconds>`
- `X-Signature: sha256=<hex_digest>`
- `X-Trace-ID: <uuid>`

Example body:

```json
{
  "message": "user message text",
  "thread_id": "uuid",
  "user_id": "uuid",
  "profile": { "locale": "en", "name": "User Name" }
}
```

## Webhook response (your endpoint -> Nexo)

Return HTTP 200 with JSON:

```json
{
  "text": "assistant reply text"
}
```

`reply` is also accepted for legacy compatibility.

## TypeScript / Python / cURL examples

- TypeScript: [examples/partner-api/proactive/typescript/](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/partner-api/proactive/typescript)
- Python: [examples/partner-api/proactive/python/](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/partner-api/proactive/python)
- cURL: [examples/partner-api/proactive/bash/](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/partner-api/proactive/bash)

## Support

- Partner portal: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com)
