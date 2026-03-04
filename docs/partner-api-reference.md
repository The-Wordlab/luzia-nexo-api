# API Reference

## Webhooks (primary integration path)

### Request

Nexo sends `POST` requests to your webhook URL.

Headers:
- `Content-Type: application/json`
- `X-App-Id: <app_uuid>`
- `X-Thread-Id: <thread_uuid>`
- `X-Timestamp: <unix_seconds>`
- `X-Signature: sha256=<hex_digest>`

Example body:

```json
{
  "event": "message_received",
  "app": {
    "id": "app_uuid",
    "name": "Restaurant Bot"
  },
  "thread": {
    "id": "thread_uuid",
    "customer_id": "user_uuid"
  },
  "message": {
    "id": "message_uuid",
    "seq": 42,
    "role": "user",
    "content_json": {},
    "content": "Book a table for 2 at 8pm"
  },
  "history_tail": [
    {
      "role": "assistant",
      "content": "Hi - I can help with bookings.",
      "content_json": {}
    }
  ],
  "profile": {
    "display_name": "María",
    "locale": "es-MX",
    "language": "es",
    "location": "Mexico City",
    "age": 32,
    "gender": "female",
    "dietary_preferences": "vegetarian",
    "preferences": {
      "cuisine": "Italian"
    }
  },
  "metadata": {},
  "timestamp": "2026-03-04T12:00:00Z"
}
```

Your webhook should parse the fields it needs and safely ignore unknown extra fields.

### Profile fields (current and upcoming)

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

### Signature verification

Verify signature before processing:
- signed payload: `"{timestamp}.{raw_json_body}"`
- algorithm: `HMAC-SHA256`
- compare with `X-Signature`

### Response formats

#### Traditional JSON

Return HTTP `200`:

```json
{
  "schema_version": "2026-03-01",
  "status": "success",
  "content_parts": [{ "type": "text", "text": "Sure - I can help with that." }],
  "cards": [],
  "actions": []
}
```

`content_parts`, `cards`, or `actions` must include at least one non-empty item.

#### SSE streaming

Return HTTP `200` + `Content-Type: text/event-stream`:

```text
data: {"type":"delta","text":"Sure - "}

data: {"type":"delta","text":"I can help with that."}

data: {"type":"done"}
```

### Retry behavior

- Nexo retries transient failures (`5xx` and timeouts).
- Nexo does not retry client errors (`4xx`).

## Partner API (optional proactive path)

Base URL:
- `https://nexo.luzia.com/api`

Authentication headers:
- `X-App-Id: <app_uuid>`
- `X-App-Secret: <app_secret>`

Core endpoints:
- `GET /apps/{app_id}/threads`
- `GET /apps/{app_id}/threads/{thread_id}/messages`
- `POST /apps/{app_id}/threads`
- `POST /apps/{app_id}/threads/{thread_id}/messages`
- `POST /apps/{app_id}/threads/{thread_id}/messages/assistant`

## Examples

- Minimal webhook snippets: [Quickstart](quickstart.md)
- All examples: [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)
- Live hosted services: [Home - Live examples](index.md#live-examples)

## Support

- Luzia Nexo: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com)
