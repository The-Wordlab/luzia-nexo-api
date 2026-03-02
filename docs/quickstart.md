# Quickstart

## 1) Implement your webhook in your backend

Your webhook should accept Nexo requests and return one of these:

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

@app.post("/webhook")
def webhook(payload: Payload):
    content = (payload.message or {}).get("content", "")
    return {"text": f"Echo: {content}"}
```

### Minimal TypeScript webhook

```ts
import express from "express";

const app = express();
app.use(express.json());

app.post("/webhook", (req, res) => {
  const content = req.body?.message?.content ?? "";
  res.json({ text: `Echo: ${content}` });
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
  -d '{"message":{"content":"hello"}}'
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
