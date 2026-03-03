# API Reference

## Webhooks (primary integration path)

### Request

Nexo sends `POST` requests to your webhook URL.

Headers:
- `Content-Type: application/json`
- `X-App-Id: <app_uuid>`
- `X-Timestamp: <unix_seconds>`
- `X-Signature: sha256=<hex_digest>`
- `X-Trace-ID: <uuid>`

Example body:

```json
{
  "message": {
    "content": "Book a table for 2 at 8pm"
  },
  "thread_id": "thread_uuid",
  "user_id": "user_uuid",
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
  }
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
  "text": "Sure - I can help with that."
}
```

`reply` is accepted as legacy fallback.

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
