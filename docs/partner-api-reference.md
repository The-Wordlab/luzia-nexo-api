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

`content_parts` must include at least one item. `cards` and `actions` are optional arrays for structured UI elements (buttons, rich cards).

#### SSE streaming

Return HTTP `200` + `Content-Type: text/event-stream`:

```text
data: {"type":"delta","text":"Sure - "}

data: {"type":"delta","text":"I can help with that."}

data: {"type":"done","schema_version":"2026-03-01","status":"success"}
```

The `done` event is required and must include `schema_version` and `status`.
It may also include `cards` and `actions` arrays (same shape as the JSON response).

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

## Push Events API (partner-initiated)

Partners push events to subscriber threads via this endpoint. Use it for live feeds — sports scores, breaking news, price alerts, flight updates — anything time-sensitive that users should receive without having to ask.

### POST /api/apps/{app_id}/events

```
POST https://nexo.luzia.com/api/apps/{app_id}/events
X-App-Secret: <app_secret>
Content-Type: application/json
```

Request body (`PartnerEvent`):

```json
{
  "event_type": "goal",
  "significance": 0.85,
  "summary": "Arsenal 2-1 Chelsea",
  "detail": "Declan Rice scores for Arsenal in the 67th minute. A long-range strike that gave Sanchez no chance. Arsenal are now two goals ahead.",
  "card": {
    "type": "match_result",
    "title": "Arsenal 2-1 Chelsea",
    "subtitle": "Premier League - Matchday 28",
    "badges": ["Premier League", "Live"],
    "fields": [
      { "label": "Goal", "value": "Rice 67'" },
      { "label": "Venue", "value": "Emirates Stadium" }
    ],
    "metadata": { "capability_state": "live" }
  },
  "subscriber_ids": ["user_001", "user_002"],
  "priority": "high",
  "character_voice": false,
  "metadata": {}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `event_type` | string | yes | Domain-specific label. e.g. `goal`, `match_start`, `breaking_news`, `price_alert` |
| `significance` | float 0-1 | yes | How important is this event? Nexo uses this for delivery decisions. |
| `summary` | string | yes | Short title used as push notification title. |
| `detail` | string | yes | Full event text delivered as the assistant message body. |
| `card` | object | no | Nexo card envelope. Rendered inline in the chat thread. |
| `subscriber_ids` | string[] | no | Target specific subscribers by `customer_id`. Omit to broadcast to all app subscribers. |
| `priority` | `"normal"` \| `"high"` | no | `"high"` triggers a push notification (requires push subscription). Default: `"normal"`. |
| `character_voice` | bool | no | Reserved for future use. Default: `false`. |
| `metadata` | object | no | Arbitrary key-value pairs passed through to `content_json`. |

Response:

```json
{
  "status": "ok",
  "delivered_to": 2,
  "push_sent": 1
}
```

| Field | Description |
|---|---|
| `delivered_to` | Number of subscriber threads that received the event message. |
| `push_sent` | Number of push notifications sent (only for `priority: "high"`). |

### Significance guide

| Score | Meaning | Delivery |
|---|---|---|
| 0.0 – 0.3 | Routine | Create thread message; no push |
| 0.3 – 0.6 | Notable | Create thread message; no push |
| 0.6 – 0.8 | Important | Thread message + card |
| 0.8 – 1.0 | Breaking | Thread message + card + push notification |

Note: push notifications are only sent when `priority: "high"` is set regardless of significance score.

### Example: push a goal notification

```bash
curl -X POST "https://nexo.luzia.com/api/apps/YOUR_APP_ID/events" \
  -H "X-App-Secret: YOUR_APP_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "goal",
    "significance": 0.85,
    "summary": "Arsenal 2-1 Chelsea",
    "detail": "Rice scores from distance in the 67th minute. Arsenal take a two-goal lead.",
    "card": {
      "type": "match_result",
      "title": "Arsenal 2-1 Chelsea",
      "subtitle": "Premier League - Matchday 28",
      "badges": ["Premier League", "Live"],
      "fields": [
        { "label": "Goal", "value": "Rice 67''" },
        { "label": "Venue", "value": "Emirates Stadium" }
      ],
      "metadata": { "capability_state": "live" }
    },
    "priority": "high"
  }'
```

### How subscriber targeting works

- `subscriber_ids` contains `customer_id` values you assigned when users connected your app.
- Omit `subscriber_ids` to deliver to all active subscribers for this app.
- For each target subscriber, Nexo finds or creates a thread scoped to your app, then appends the event as an assistant message.
- Users can reply in the same thread — replies are forwarded to your webhook endpoint as normal.

### Pattern: live feed partner

A partner that sends events continuously:

1. **Ingest data** on a background loop (RSS, APIs, websockets)
2. **Detect events** worth notifying using rules + LLM classification
3. **Score significance** — not everything deserves a push
4. **Call this endpoint** with the event, card, and target subscribers

See [examples-showcase.md](examples-showcase.md) for a working implementation in the sports-rag example.

---

## App lifecycle

Apps follow a review workflow before they become available to users:

1. **draft** - initial state after creation
2. **submitted** - partner submits the app for review via `POST /apps/{app_id}/submit`
3. **approved** - Nexo team approves the app (it now appears in the catalog)
4. **rejected** - Nexo team rejects the app with a reason; partner can fix and resubmit via `POST /apps/{app_id}/resubmit`

Only `draft` and `rejected` apps can be submitted for review.

## Catalog API

Public endpoint for app discovery (no authentication required):

- `GET /api/catalog/apps` - returns all approved apps as lightweight entries

## TypeScript SDK

The `@nexo/partner-sdk` package provides:

- Webhook signature verification (`verifyWebhookSignature`)
- Typed webhook payload parsing (`parseWebhookPayload`)
- Proactive messaging client (`NexoClient`)

See the [SDK README](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/sdk/javascript) for install and usage.

## Examples

- Minimal webhook snippets: [Quickstart](quickstart.md)
- All examples: [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)
- Live hosted services: [Home - Live examples](index.md#live-examples)

## Support

- Luzia Nexo: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com)
