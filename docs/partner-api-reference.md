# Partner API Reference

Base URL:
- `https://nexo.luzia.com/api`

Authentication headers:
- `X-App-Id: <app_uuid>`
- `X-App-Secret: <app_secret>`

## Core endpoints

- `GET /apps/{app_id}/threads`
- `GET /apps/{app_id}/threads/{thread_id}/messages`
- `POST /apps/{app_id}/threads`
- `POST /apps/{app_id}/threads/{thread_id}/messages`
- `POST /apps/{app_id}/threads/{thread_id}/messages/assistant`

## Webhook request

Nexo calls your webhook with:
- `Content-Type: application/json`
- `X-App-Id`
- `X-Timestamp`
- `X-Signature`
- `X-Trace-ID`

## Webhook response formats

### Traditional JSON response

```json
{
  "text": "assistant reply text"
}
```

`reply` is accepted as a legacy fallback.

### SSE streaming response

Use `Content-Type: text/event-stream` and stream events.

```text
data: {"type":"delta","text":"hello "}

data: {"type":"delta","text":"world"}

data: {"type":"done"}
```

## Example code

- Webhook examples: [Examples](examples.md)
- Partner API examples: [Examples](examples.md)

## Support

- Partner portal: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com)
