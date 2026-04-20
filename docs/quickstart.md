# Quickstart

Ship your first Nexo Partner Integration in minutes, then expand to richer experiences.

This page covers the **webhook-backed Partner Integration lane**. If you want to create first-party structured apps for a user through the Nexo API or MCP, use the [Personalized Apps API](micro-apps-api.md) guide instead. For apps that need reference data and derived outputs, see [Knowledge Packs](knowledge-packs.md).

## What you need

- A webhook endpoint in your backend: `POST /webhook`
- One shared secret: `WEBHOOK_SECRET`
- Your app configured in Nexo with `webhook_url` and `WEBHOOK_SECRET`

Everything else in this docs site is optional capability expansion.

## 1) Implement your webhook

Your webhook receives a request from Nexo and returns a response envelope.

**Profile context:** Webhook payloads may include approved profile attributes such as `locale`, `language`, `location`, `age`, `date_of_birth`, `gender`, and `dietary_preferences`. Nexo manages consent collection and scope enforcement before sending profile data to your webhook. Parse defensively and ignore unknown fields.

### JSON response

```json
{
  "schema_version": "2026-03",
  "task": { "id": "tsk_1", "status": "completed" },
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
      "schema_version": "2026-03",
      "task": {"id": "tsk_1", "status": "completed"},
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
    schema_version: "2026-03",
    task: { id: "tsk_1", status: "completed" },
    content_parts: [{ type: "text", text }],
  });
});
```

## 2) Configure Nexo

This step connects Nexo to your webhook in production. For local-only testing, skip to step 4.

1. Go to [nexo.luzia.com](https://nexo.luzia.com)
2. Create or open your Partner Integration
3. Set your webhook URL and `WEBHOOK_SECRET`
4. Send a test message and verify logs on your backend

## 3) Validate request handling

Checklist:

- Verify `X-App-Id`
- Verify timestamp and signature (`X-Timestamp`, `X-Signature`)
- Return valid JSON or SSE stream

### Signature verification — Python (FastAPI)

```python
import hmac
import hashlib
import time
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

WEBHOOK_SECRET = "your_webhook_secret"

def verify_signature(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    # Reject requests with a timestamp older than 5 minutes
    if abs(time.time() - int(timestamp)) > 300:
        return False
    payload = f"{timestamp}.{body.decode()}"
    expected = "sha256=" + hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Timestamp", "")
    signature = request.headers.get("X-Signature", "")

    if not verify_signature(WEBHOOK_SECRET, timestamp, body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    # ... process payload
```

### Signature verification — TypeScript (Express)

```typescript
import crypto from "crypto";
import express, { Request, Response, NextFunction } from "express";

const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET ?? "";

function verifySignature(
  secret: string,
  timestamp: string,
  body: string,
  signature: string
): boolean {
  // Reject requests with a timestamp older than 5 minutes
  if (Math.abs(Date.now() / 1000 - parseInt(timestamp)) > 300) return false;
  const payload = `${timestamp}.${body}`;
  const expected =
    "sha256=" +
    crypto.createHmac("sha256", secret).update(payload).digest("hex");
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  );
}

// Use express.raw to access the raw body for signature verification
app.post("/webhook", express.raw({ type: "application/json" }), (req: Request, res: Response) => {
  const timestamp = req.headers["x-timestamp"] as string ?? "";
  const signature = req.headers["x-signature"] as string ?? "";
  const body = req.body as Buffer;

  if (!verifySignature(WEBHOOK_SECRET, timestamp, body.toString(), signature)) {
    res.status(401).json({ error: "Invalid signature" });
    return;
  }

  const payload = JSON.parse(body.toString());
  // ... process payload
});
```

## 4) Test your webhook directly

```bash
curl -X POST "http://localhost:8080/webhook" \
  -H "Content-Type: application/json" \
  -d '{"event":"message_received","app":{"id":"app-uuid","name":"Demo"},"thread":{"id":"thread-uuid","customer_id":"user-123"},"message":{"id":"msg-uuid","seq":1,"role":"user","content":"hello","content_json":{}},"history_tail":[],"profile":{"display_name":"María","locale":"es-MX","dietary_preferences":"vegetarian"},"metadata":{},"timestamp":"2026-03-04T12:00:00Z"}'
```

Expected response:

```json
{
  "schema_version": "2026-03",
  "task": { "id": "tsk_1", "status": "completed" },
  "content_parts": [{ "type": "text", "text": "Your assistant response" }]
}
```

## 5) Submit your app for review

Once your webhook is working and configured in the partner portal, submit your Partner Integration for review:

1. Go to your app in [nexo.luzia.com](https://nexo.luzia.com)
2. Click **Submit for review**
3. The Nexo team will approve or provide feedback
4. Once approved, your app appears in the public catalog

See [Partner API Reference - App lifecycle](partner-api-reference.md#app-lifecycle) for the full workflow.

## Next steps

- Full contract and examples: [Partner API Reference](partner-api-reference.md)
- TypeScript SDK: [SDK README](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/sdk/javascript)
- Examples folder: [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)
- OpenClaw Bridge example: [examples/webhook/openclaw-bridge](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/openclaw-bridge)
- Signed webhook examples:
  - Python: [examples/webhook/minimal/python/server.py](https://github.com/The-Wordlab/luzia-nexo-api/blob/main/examples/webhook/minimal/python/server.py)
  - TypeScript: [examples/webhook/minimal/typescript/webhook-server.mjs](https://github.com/The-Wordlab/luzia-nexo-api/blob/main/examples/webhook/minimal/typescript/webhook-server.mjs)
- Hosting and deployment: [Hosting](hosting.md)
- GCP deployment playbook: [GCP Deploy Playbook](gcp-deploy-playbook.md)

## Personalized Apps: Quick start

Create structured apps from the terminal using MCP.

### What you need

- A Nexo account (or a local Nexo runtime - see [local setup](mcp.md#local-development-with-the-nexo-runtime))
- A developer key (from Dashboard -> Profile -> Developer Access)

### Connect

```bash
export NEXO_DEVELOPER_KEY=nexo_uak_...
export NEXO_BASE_URL=http://localhost:8000
claude mcp add --scope project --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"
```

### Build

Open Claude Code and describe the app you want:

> "Create a meal planner with weekly menus and a shopping list"

For the full API reference, see [Personalized Apps API](micro-apps-api.md).
For MCP tool details, see [MCP Server](mcp.md).
For a step-by-step walkthrough, see [Tutorial: Create an app from the terminal](tutorial-create-app-from-terminal.md).

## What to build next

Once your webhook is working, consider these patterns:

### Add rich cards and actions

Return `cards` and `actions` alongside `content_parts` to give users structured UI:

```json
{
  "schema_version": "2026-03",
  "task": { "id": "tsk_1", "status": "completed" },
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
  "metadata": {
    "prompt_suggestions": [
      "Show me another angle",
      "Summarize this in 3 bullets"
    ]
  },
  "actions": [
    { "id": "read_1", "label": "Read full article", "url": "https://example.com/article", "style": "secondary" }
  ]
}
```

`metadata.prompt_suggestions` renders as contextual clickable chips in chat.

For starter chips before any message is sent, publish prompt suggestions from `GET /.well-known/agent.json` under `capabilities.items[].metadata.prompt_suggestions`.

### Add RAG

If your integration has a knowledge base (news, product catalog, documentation), add retrieval-augmented generation. See the production examples:

- [News Feed RAG](examples-showcase.md#news-feed-rag) -- RSS + vector retrieval + LLM + source cards
- [Sports Feed RAG](examples-showcase.md#sports-feed-rag) -- Live match data + intent detection + streaming
- [Travel RAG](examples-showcase.md#travel-rag) -- Destination guides + itinerary advice
- [Football Live RAG](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/football-live/python) -- Live scores, standings, and top scorers

### Add vertical orchestration

For multi-step flows beyond Q&A, start from the flagship vertical examples:

- [Routines](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/routines/python) -- Morning briefings, schedule actions, follow-up reminders
- [Food Ordering](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/food-ordering/python) -- Discovery, basket building, checkout approval, delivery tracking
- [Travel Planning](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples/webhook/travel-planning/python) -- Itinerary planning, flight comparison, booking handoff, budget guidance, disruption replanning

### Add live event push

For time-sensitive data (scores, price changes, flight updates, breaking news), push events proactively to subscriber threads:

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

Full reference: [Partner API Reference - Push Events API](partner-api-reference.md#push-events-api-partner-initiated)
