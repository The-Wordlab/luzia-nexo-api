# Quickstart

## 1) Implement your webhook in your backend

Your webhook should accept Nexo requests and return one of these:

Profile note:
- Webhook payloads can include consented profile attributes such as `locale`, `language`, `location`, `age`, `date_of_birth`, `gender`, and `dietary_preferences`.
- Availability depends on app permissions and user consent.
- Additional attributes are added over time while keeping backward compatibility.
- Parse defensively and ignore unknown fields.

### JSON response

```json
{
  "text": "Your assistant response"
}
```

### SSE response

Use `Content-Type: text/event-stream` and stream `delta` events followed by `done`.

### Minimal Python webhook

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

### Minimal TypeScript webhook

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

## 2) Configure Nexo

1. Go to [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
2. Create or open your app
3. Set your webhook URL and secret
4. Send a test message and verify logs on your backend

## 3) Validate request handling

Checklist:
- verify `X-App-Id`
- verify timestamp/signature (`X-Timestamp`, `X-Signature`)
- return valid JSON or SSE stream

## 4) Test your webhook directly

Example local test:

```bash
curl -X POST "http://localhost:8080/webhook" \
  -H "Content-Type: application/json" \
  -d '{"message":{"content":"hello"},"profile":{"display_name":"María","locale":"es-MX","dietary_preferences":"vegetarian"}}'
```

Expected response shape:

```json
{
  "text": "Your assistant response"
}
```

## Next

- Full contract and examples: [API Reference](partner-api-reference.md)
- Direct examples folder: [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)
- Signed webhook examples:
  - Python: [examples/webhook/minimal/python/server.py](https://github.com/The-Wordlab/luzia-nexo-api/blob/main/examples/webhook/minimal/python/server.py)
  - TypeScript: [examples/webhook/minimal/typescript/webhook-server.mjs](https://github.com/The-Wordlab/luzia-nexo-api/blob/main/examples/webhook/minimal/typescript/webhook-server.mjs)
- Optional hosting/deployment examples: [Hosting (Optional)](hosting.md)
