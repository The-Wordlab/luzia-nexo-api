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
    "locale": "en"
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

Main folder:
- [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)

### Minimal webhook snippet (Python)

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Payload(BaseModel):
    message: dict | None = None
    profile: dict | None = None

@app.post("/webhook")
def webhook(payload: Payload):
    content = (payload.message or {}).get("content", "")
    profile = payload.profile or {}
    name = profile.get("display_name") or profile.get("name")
    locale = profile.get("locale") or profile.get("language")
    dietary = profile.get("dietary_preferences")
    text = f"{name}, you said: {content}" if name else f"Echo: {content}"
    hints = [h for h in [f"locale={locale}" if locale else None, f"dietary={dietary}" if dietary else None] if h]
    return {"text": f"{text} ({', '.join(hints)})" if hints else text}
```

### Minimal webhook snippet (TypeScript)

```ts
import express from "express";

const app = express();
app.use(express.json());

app.post("/webhook", (req, res) => {
  const content = req.body?.message?.content ?? "";
  const profile = req.body?.profile ?? {};
  const name = profile.display_name ?? profile.name ?? null;
  const locale = profile.locale ?? profile.language ?? null;
  const dietary = profile.dietary_preferences ?? null;
  let text = name ? `${name}, you said: ${content}` : `Echo: ${content}`;
  const hints = [];
  if (locale) hints.push(`locale=${locale}`);
  if (dietary) hints.push(`dietary=${dietary}`);
  if (hints.length) text = `${text} (${hints.join(", ")})`;
  res.json({ text });
});
```

Hosted endpoints:
- Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/)
- TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/)

## Support

- Luzia Nexo: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com)
