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
  "schema_version": "2026-03-01",
  "status": "success",
  "content_parts": [{ "type": "text", "text": "Your assistant response" }]
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
    event: str | None = None
    app: dict | None = None
    thread: dict | None = None
    message: dict | None = None
    history_tail: list[dict] | None = None
    profile: dict | None = None
    metadata: dict | None = None
    timestamp: str | None = None

@app.post("/webhook")
def webhook(payload: Payload):
    content = (payload.message or {}).get("content", "")
    profile = payload.profile or {}
    name = profile.get("display_name") or profile.get("name")
    locale = profile.get("locale") or profile.get("language")
    dietary = profile.get("dietary_preferences")
    text = f"{name}, you said: {content}" if name else f"Echo: {content}"
    hints = [h for h in [f"locale={locale}" if locale else None, f"dietary={dietary}" if dietary else None] if h]
    return {
      "schema_version": "2026-03-01",
      "status": "success",
      "content_parts": [{"type": "text", "text": f"{text} ({', '.join(hints)})" if hints else text}],
    }
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
  res.json({
    schema_version: "2026-03-01",
    status: "success",
    content_parts: [{ type: "text", text }],
  });
});
```

## 2) Configure Nexo

This step is only required when you want Nexo to call your webhook in live integration mode.
For independent local testing, skip to step 4 and hit your local webhook directly with curl.

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
  -d '{"event":"message_received","app":{"id":"app-uuid","name":"Demo"},"thread":{"id":"thread-uuid","customer_id":"user-123"},"message":{"id":"msg-uuid","seq":1,"role":"user","content":"hello","content_json":{}},"history_tail":[],"profile":{"display_name":"María","locale":"es-MX","dietary_preferences":"vegetarian"},"metadata":{},"timestamp":"2026-03-04T12:00:00Z"}'
```

Expected response shape:

```json
{
  "schema_version": "2026-03-01",
  "status": "success",
  "content_parts": [{ "type": "text", "text": "Your assistant response" }]
}
```

## 5) Submit your app for review

Once your webhook is working and configured in the partner portal, submit your app for review:

1. Go to your app in [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
2. Click **Submit for review**
3. The Nexo team will approve or reject with feedback
4. Once approved, your app appears in the public catalog

See [API Reference - App lifecycle](partner-api-reference.md#app-lifecycle) for the full workflow.

## Next

- Full contract and examples: [API Reference](partner-api-reference.md)
- TypeScript SDK: [SDK README](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/sdk/javascript)
- Direct examples folder: [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)
- OpenClaw Bridge example: [examples/webhook/openclaw-bridge](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/openclaw-bridge)
- Signed webhook examples:
  - Python: [examples/webhook/minimal/python/server.py](https://github.com/The-Wordlab/luzia-nexo-api/blob/main/examples/webhook/minimal/python/server.py)
  - TypeScript: [examples/webhook/minimal/typescript/webhook-server.mjs](https://github.com/The-Wordlab/luzia-nexo-api/blob/main/examples/webhook/minimal/typescript/webhook-server.mjs)
- Optional hosting/deployment examples: [Hosting (Optional)](hosting.md)

## What to build next

Once your webhook is working, consider these patterns:

### Add rich cards and actions

Return `cards` and `actions` alongside `content_parts` to give users structured UI:

```json
{
  "schema_version": "2026-03-01",
  "status": "success",
  "content_parts": [{ "type": "text", "text": "Here are today's top stories." }],
  "cards": [
    {
      "type": "source",
      "title": "Article title",
      "subtitle": "Publisher — date",
      "description": "Excerpt...",
      "metadata": { "url": "https://example.com/article" }
    }
  ],
  "actions": [
    { "id": "read_1", "label": "Read full article", "url": "https://example.com/article", "style": "secondary" }
  ]
}
```

### Add RAG

If your integration has a knowledge base (news, product catalogue, documentation), add retrieval-augmented generation. See the production examples:

- [News Feed RAG](examples-showcase.md#news-feed-rag) — RSS + ChromaDB + LLM + source cards
- [Sports Feed RAG](examples-showcase.md#sports-feed-rag) — Live match data + intent detection + streaming
- [Travel RAG](examples-showcase.md#travel-rag) — Destination guides + itinerary advice

### Add live event push

If your domain has time-sensitive data (scores, price changes, flight updates, breaking news), push events proactively to subscriber threads:

```bash
curl -X POST "https://nexo.luzia.com/api/apps/YOUR_APP_ID/events" \
  -H "X-App-Secret: YOUR_APP_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "price_drop",
    "significance": 0.75,
    "summary": "MacBook Pro 30% off",
    "detail": "The MacBook Pro M4 is now $1399, down from $1999. Deal expires in 4 hours.",
    "card": {
      "type": "product",
      "title": "MacBook Pro M4",
      "subtitle": "$1399 (was $1999)",
      "badges": ["30% off", "Limited time"],
      "metadata": { "url": "https://store.example.com/macbook" }
    },
    "priority": "high"
  }'
```

Full reference: [API Reference - Push Events API](partner-api-reference.md#push-events-api-partner-initiated)
