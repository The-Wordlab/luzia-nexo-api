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
  "message": "Book a table for 2 at 8pm",
  "thread_id": "thread_uuid",
  "user_id": "user_uuid",
  "profile": {
    "locale": "en"
  }
}
```

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

@app.post("/webhook")
def webhook(payload: Payload):
    content = (payload.message or {}).get("content", "")
    return {"text": f"Echo: {content}"}
```

### Minimal webhook snippet (TypeScript)

```ts
import express from "express";

const app = express();
app.use(express.json());

app.post("/webhook", (req, res) => {
  const content = req.body?.message?.content ?? "";
  res.json({ text: `Echo: ${content}` });
});
```

Hosted endpoints:
- Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/)
- TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/)

## Support

- Luzia Nexo: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com)
