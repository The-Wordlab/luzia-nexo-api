# Partner API Reference

This page documents the **Partner Integration** contract: external webhook-backed apps that run on your infrastructure.

If you are building first-party structured apps through Nexo itself, use the [Personalized Apps API](micro-apps-api.md) guide instead.

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
    "country": "MX",
    "email": "maria@example.com",
    "preferences": {
      "cuisine": "Italian"
    },
    "facts": [
      { "key": "dietary", "value": "vegetarian" }
    ]
  },
  "locale": "es-MX",
  "locale_source": "profile",
  "tools": [
    { "name": "websearch", "enabled": true }
  ],
  "connectors": [
    {
      "type": "google_calendar",
      "status": "active",
      "scopes": ["read", "write"],
      "token_endpoint": "https://oauth2.googleapis.com/token"
    }
  ],
  "metadata": {},
  "timestamp": "2026-03-04T12:00:00Z"
}
```

Your webhook should parse the fields it needs and safely ignore unknown extra fields.

### Request fields reference

| Field | Type | Required | Description |
|---|---|---|---|
| `event` | string | yes | Always `"message_received"` for user messages. |
| `app` | object | yes | `{ "id": "...", "name": "..." }` - the app receiving the message. |
| `thread` | object | yes | `{ "id": "...", "customer_id": "..." }` - conversation thread. |
| `message` | object | yes | The user message. See below. |
| `history_tail` | array | no | Up to 10 recent messages for context. |
| `profile` | object | no | Approved profile attributes (requires user consent). |
| `locale` | string | no | Resolved locale for this turn (e.g. `es-MX`). |
| `locale_source` | string | no | How the locale was resolved (`profile`, `browser`, `default`). |
| `tools` | array | no | Tool configurations enabled for this app. |
| `attachments` | array | no | Uploaded media references (`media_id`, `type`, `url`). |
| `connectors` | array | no | Active connector grants the user has linked. |
| `metadata` | object | no | Arbitrary key-value pairs from the runtime. |
| `timestamp` | string | yes | ISO 8601 timestamp. |

### Profile fields

Webhook payloads may include approved profile attributes inside the `profile` object:

| Field | Type | Description |
|---|---|---|
| `display_name` | string | User's display name. |
| `locale` | string | User's locale (e.g. `es-MX`). |
| `country` | string | Country code (e.g. `MX`). |
| `email` | string | User's email address. |
| `preferences` | object | Key-value preferences (e.g. `{"cuisine": "Italian"}`). |
| `facts` | array | Structured facts as `[{"key": "...", "value": "..."}]`. |

The profile model accepts extra fields transparently (e.g. provenance metadata), so your webhook may receive additional attributes beyond those listed here. Parse defensively and ignore unknown fields - the schema is backward-compatible as new attributes are added.

Availability depends on app permissions and user consent. Nexo manages consent collection and only proxies the approved scoped profile fields to your webhook.

### Connectors

When the user has linked external services, the `connectors` array provides grant details:

| Field | Type | Description |
|---|---|---|
| `type` | string | Connector type (e.g. `google_calendar`). |
| `status` | string | Grant status (`active`, `expired`, `revoked`). |
| `scopes` | array | Granted scopes. |
| `token_endpoint` | string | OAuth token endpoint URL (when available). |

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
  "schema_version": "2026-03",
  "task": { "id": "tsk_1", "status": "completed" },
  "content_parts": [{ "type": "text", "text": "Sure - I can help with that." }],
  "cards": [],
  "actions": [],
  "metadata": {
    "prompt_suggestions": ["Show me options", "Track status"]
  }
}
```

**Required fields:**

- `schema_version` - contract version string (currently `"2026-03"`).
- `task` - A2A-aligned lifecycle metadata with `id` and `status`. See [Task lifecycle](#task-lifecycle) below.
- At least one non-empty array among `content_parts`, `cards`, `actions`, or `artifacts`.

**Optional fields:**

- `cards` - structured UI elements rendered inline in the chat thread.
- `actions` - buttons rendered below the card block.
- `artifacts` - transport-neutral output payloads (files, structured data).
- `capability` - metadata about the producing agent (`name`, `version`).
- `error` - structured error payload (required when `task.status` is `"failed"`).
- `metadata` - arbitrary key-value pairs. `metadata.prompt_suggestions` provides contextual next-prompt chips (up to 5 strings).
- `locale` - BCP-47 locale of the response content.
- `extensions` - partner-specific data passed through transparently.

For demo discovery and onboarding, hosted examples should also publish starter
prompt chips from `GET /.well-known/agent.json` under
`capabilities.items[].metadata.prompt_suggestions`.

#### Task lifecycle

The `task` object carries A2A-aligned lifecycle metadata:

```json
{
  "task": {
    "id": "tsk_1",
    "status": "completed",
    "can_retry": false,
    "can_cancel": false,
    "message": "Booking confirmed"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable task identifier. |
| `status` | string | Lifecycle state (see values below). |
| `can_retry` | boolean | Whether the client can retry on failure. |
| `can_cancel` | boolean | Whether the client can cancel the task. |
| `message` | string | Human-readable status message. |

**Status values:**

| Value | Meaning |
|---|---|
| `queued` | Task accepted, not yet started. |
| `in_progress` | Task is actively processing. |
| `requires_input` | Task is waiting for additional user input. |
| `completed` | Task finished successfully. |
| `failed` | Task failed. Include an `error` object. |
| `canceled` | Task was canceled. |

!!! warning "Legacy `status` field"
    The top-level `status` field is no longer accepted without `task.status`. Always use the canonical `task` object. Responses with only a top-level `status` will be rejected by the validator.

#### Capability metadata

Declare what produced the response:

```json
{
  "capability": {
    "name": "news.search",
    "version": "2.1"
  }
}
```

#### Artifacts

Return structured output payloads alongside text:

```json
{
  "artifacts": [
    {
      "type": "application/json",
      "name": "booking_details",
      "data": { "booking_id": "BKG-20483", "status": "confirmed" }
    },
    {
      "type": "image/png",
      "name": "receipt",
      "url": "https://example.com/receipts/BKG-20483.png",
      "mime_type": "image/png"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | Content type or MIME type. |
| `name` | string | Human-readable name for the artifact. |
| `mime_type` | string | MIME type when `type` alone is ambiguous. |
| `data` | any | Inline structured data. |
| `url` | string | URL to fetch the artifact content. |

#### SSE streaming

Return HTTP `200` + `Content-Type: text/event-stream`.

The canonical SSE event vocabulary:

| Event type | When emitted | Payload |
|---|---|---|
| `stream_start` | First event - signals stream beginning | `{}` (empty, or optional metadata) |
| `content_delta` | Each text chunk from the LLM | `{"text": "<chunk>"}` |
| `done` | Final event - full response metadata | Schema below |
| `enrichment` | Reserved for future use - cards/actions mid-stream | - |
| `error` | Reserved for future use - standalone error event | - |

Example stream:

```text
event: stream_start
data: {}

event: content_delta
data: {"text":"Sure - "}

event: content_delta
data: {"text":"I can help with that."}

event: done
data: {"schema_version":"2026-03","task":{"id":"tsk_1","status":"completed"},"text":"Sure - I can help with that.","metadata":{"prompt_suggestions":["Show me options","Track status"]}}
```

The `done` event is required and must include `schema_version` and `task.status`.
It should also include `text` (the full accumulated response text).
It may also include `cards`, `actions`, `artifacts`, and `capability` (same shape as the JSON response).

#### Streaming behavior details

| Aspect | Behavior |
|---|---|
| **Delivery guarantee** | Best-effort for streaming (at-least-once for sync JSON) |
| **Keepalive** | No heartbeat events - the stream stays open until `done` or timeout |
| **Reconnection** | Client should not reconnect mid-stream. If the connection drops before `done`, treat the response as failed and show an error to the user |
| **Error during stream** | If your webhook encounters an error mid-stream, emit a `done` event with `task.status: "failed"` and an `error` object. Do not simply close the connection |
| **Timeout** | 8 seconds from connection open to first byte, then unlimited for active streams |
| **Max stream duration** | No hard limit, but responses over 60 seconds may be interrupted by load balancers |

#### Error event format

If your webhook needs to signal an error during streaming, emit a `done` event with `task.status: "failed"` and an `error` object:

```text
event: done
data: {"schema_version":"2026-03","task":{"id":"tsk_err","status":"failed"},"error":{"code":"upstream_timeout","message":"Could not reach booking system","retryable":true}}
```

### Retry behavior

Nexo retries webhook failures using exponential backoff:

| Attempt | Delay | Condition |
|---|---|---|
| 1st retry | ~1 second | `5xx` response or connection timeout |
| 2nd retry | ~4 seconds | `5xx` response or connection timeout |
| 3rd retry | ~16 seconds | `5xx` response or connection timeout |

- **No retry** on `4xx` errors (client errors are considered permanent).
- **No retry** on stream-mode responses (only the connection attempt is retried, not mid-stream failures).
- **Idempotency**: Retried requests carry the same `X-Thread-Id` and message content. Your webhook should handle duplicate deliveries gracefully.

### Card types

The `cards` array in your webhook response renders structured UI elements inline in the chat thread. All card fields are optional — the renderer handles any card shape gracefully and only shows the fields you provide.

#### Common card shapes

##### Info card

Best for structured data with labelled key-value pairs.

```json
{
  "type": "info",
  "title": "Booking Confirmed",
  "subtitle": "La Piazzetta — Tonight at 8:00 PM",
  "description": "Your table for 2 is confirmed. Cancellation window closes at 6:00 PM.",
  "icon": "🍽️",
  "badges": ["Confirmed", "Vegetarian options"],
  "fields": [
    { "label": "Date", "value": "Monday, 17 Mar" },
    { "label": "Time", "value": "8:00 PM" },
    { "label": "Party size", "value": "2 guests" },
    { "label": "Reference", "value": "BKG-20483" }
  ],
  "metadata": { "capability_state": "live" }
}
```

##### Image card

Best for visual content — products, destinations, articles, recipes.

```json
{
  "type": "image",
  "title": "MacBook Pro M4",
  "subtitle": "$1,399 — 30% off today only",
  "image_url": "https://example.com/images/macbook-pro.jpg",
  "description": "14-inch, 24GB RAM, 512GB SSD. Eligible for free next-day delivery.",
  "badges": ["In stock", "Free delivery"]
}
```

##### Match result card

Best for live sports scores and standings.

```json
{
  "type": "match_result",
  "title": "Arsenal 2 – 1 Chelsea",
  "subtitle": "Premier League · Matchday 28",
  "badges": ["Live", "67'"],
  "fields": [
    { "label": "Last goal", "value": "Rice 67'" },
    { "label": "Venue", "value": "Emirates Stadium" },
    { "label": "Attendance", "value": "60,288" }
  ],
  "metadata": { "capability_state": "live" }
}
```

##### Source card

Best for citations, search results, and article references.

```json
{
  "type": "source",
  "title": "Bank of England holds interest rate at 4.5%",
  "subtitle": "Reuters · 16 Mar 2026",
  "description": "The Monetary Policy Committee voted 7-2 to hold rates, citing persistent services inflation.",
  "metadata": { "url": "https://reuters.com/article/..." }
}
```

##### Action card

Best for multi-step flows where the user needs to choose or confirm.

```json
{
  "type": "action",
  "title": "Confirm your order",
  "description": "Margherita pizza + sparkling water — total €18.50. Estimated delivery: 30 min."
}
```

Pair action cards with an `actions` array in the same response to render confirmation buttons below the card block.

#### Fields reference

| Field | Type | Description |
|---|---|---|
| `type` | string | Card variant hint. Any string is accepted; documented types get optimised rendering. |
| `title` | string | Primary heading. |
| `subtitle` | string | Secondary line shown below title. |
| `description` | string | Body text or excerpt. |
| `icon` | string | Emoji or single character rendered as an avatar icon. |
| `image_url` | string | Full URL of an image to display (HTTPS recommended). |
| `badges` | string[] | Short label chips rendered as pills (e.g. `"Live"`, `"Free delivery"`). |
| `rating` | number | Numeric rating 0–5; renders as star icons. |
| `fields` | object[] | Label-value pairs. See below. |
| `metadata` | object | Arbitrary key-value pairs. `capability_state` has special rendering (see below). |

#### `fields` array format

```json
"fields": [
  { "label": "Departure", "value": "London Heathrow — 09:15" },
  { "label": "Arrival", "value": "Barcelona El Prat — 12:40" },
  { "label": "Status", "value": "On time" }
]
```

Each entry must have `label` and `value` as strings. Fields render as a two-column grid with the label in uppercase and the value below it.

#### `metadata.capability_state` values

Set `capability_state` inside a card's `metadata` object to signal the data freshness to users:

| Value | Badge shown | When to use |
|---|---|---|
| `"live"` | Live | Card data comes from a real-time source (live scores, live inventory) |
| `"simulated"` | Demo | Card data is mocked or seeded (demos, sandbox environments) |
| `"requires_connector"` | Connect required | Feature needs a third-party connector the user has not yet authorised |

#### `actions` array format

`actions` are independent of `cards` and render as a row of buttons below the card block. Return them at the top level of your webhook response alongside `cards`.

```json
"actions": [
  { "id": "confirm_booking", "label": "Confirm", "style": "primary" },
  { "id": "cancel_booking", "label": "Cancel", "style": "secondary" },
  { "id": "view_details", "label": "View details", "url": "https://example.com/booking/BKG-20483", "style": "secondary" }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable identifier for the action. |
| `label` | string | Button text shown to the user. |
| `style` | `"primary"` \| `"secondary"` | Visual weight. Default: `"secondary"`. |
| `url` | string | Optional URL to open when clicked. |

### Error handling

#### HTTP status codes

When your webhook calls the Partner API (the proactive path), Nexo returns standard HTTP status codes:

| Code | Meaning |
|---|---|
| `200` | Success. |
| `400` | Bad request — malformed JSON or invalid field values. |
| `401` | Unauthorized — `X-App-Secret` missing or invalid. |
| `403` | Forbidden — the app exists but the secret does not match, or the operation is not permitted. |
| `404` | Not found — the app, thread, or message ID does not exist. |
| `422` | Validation error — the request body is structurally valid JSON but fails schema validation. |
| `500` | Internal error — a transient Nexo-side failure. Safe to retry with exponential backoff. |

#### Error response format

All error responses use the same body shape:

```json
{
  "detail": "Human-readable description of the error"
}
```

For `422` validation errors the `detail` field may be an array of objects describing each failing field:

```json
{
  "detail": [
    {
      "loc": ["body", "significance"],
      "msg": "Input should be less than or equal to 1",
      "type": "less_than_equal"
    }
  ]
}
```

#### Webhook failure conditions

Nexo treats a webhook call as failed when any of the following occur:

- Your endpoint returns a non-2xx HTTP status.
- The response body is not valid JSON (for non-SSE responses).
- Required fields are missing (`schema_version`, `task` object with `status`, and at least one non-empty array among `content_parts`, `cards`, `actions`, or `artifacts`).
- The response takes longer than **8 seconds** to begin.

#### Retry policy

| Condition | Retried? |
|---|---|
| `5xx` from your webhook | Yes — up to 3 retries with exponential backoff |
| Timeout (> 8 seconds) | Yes — up to 3 retries |
| `4xx` from your webhook | No — fix the response before retrying manually |
| Invalid JSON or missing fields | No — correct the response shape |

Retries use exponential backoff: 1 s, 4 s, 16 s.

#### Structured error field in webhook responses

When your webhook cannot fulfil a request, return a structured `error` object alongside a user-facing message in `content_parts`. This lets Nexo distinguish retriable failures from permanent ones:

```json
{
  "schema_version": "2026-03",
  "task": { "id": "tsk_123", "status": "failed" },
  "error": {
    "code": "booking_unavailable",
    "message": "No tables available for the requested time",
    "retryable": false
  },
  "content_parts": [
    { "type": "text", "text": "Sorry, there are no tables available at that time. Would you like me to check a different slot?" }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `error.code` | string | Machine-readable error code specific to your domain. |
| `error.message` | string | Developer-facing description (not shown directly to users). |
| `error.retryable` | boolean | Whether Nexo should retry on the next user message. |
| `error.retry_after_ms` | int | Optional. How long to wait before retrying (milliseconds). |
| `error.details` | object | Optional. Additional structured context for debugging. |

`task.status` must be `"failed"` when returning an `error` object. The `content_parts` message is what the user sees.

### Full response schema reference

The complete response envelope with all optional fields:

```json
{
  "schema_version": "2026-03",
  "task": {
    "id": "tsk_1",
    "status": "completed",
    "can_retry": false,
    "can_cancel": false,
    "message": "Done"
  },
  "content_parts": [
    { "type": "text", "text": "Here is your result." }
  ],
  "cards": [],
  "actions": [],
  "artifacts": [
    { "type": "application/json", "name": "result", "data": {} }
  ],
  "capability": {
    "name": "restaurant.booking",
    "version": "1.0"
  },
  "error": null,
  "metadata": {
    "prompt_suggestions": ["Show me options"]
  },
  "locale": "es-MX",
  "extensions": {}
}
```

## Partner API (optional proactive path)

Use the Partner API to create threads, read conversation history, and inject messages without waiting for a user to send a message first. This is the proactive path — useful for onboarding flows, scheduled briefings, and follow-ups.

Base URL: `https://nexo.luzia.com/api`

All requests require two authentication headers:

```
X-App-Id: <app_uuid>
X-App-Secret: <app_secret>
```

### POST /apps/{app_id}/threads

Create a new conversation thread for a user. Nexo returns the thread object plus an initial greeting message from the assistant.

**Request body** (all fields optional):

```json
{
  "title": "Weekly briefing",
  "customer_id": "user_001"
}
```

| Field | Type | Description |
|---|---|---|
| `title` | string | Optional display title for the thread. |
| `customer_id` | string | Your identifier for the user (max 128 chars). Used for subscriber targeting in push events. |

**Response:**

```json
{
  "thread": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "app_id": "app_uuid",
    "title": "Weekly briefing",
    "customer_id": "user_001",
    "status": "active",
    "created_at": "2026-03-16T09:00:00Z",
    "updated_at": "2026-03-16T09:00:00Z"
  },
  "initial_message": {
    "id": "msg_uuid",
    "thread_id": "550e8400-e29b-41d4-a716-446655440000",
    "seq": 1,
    "role": "assistant",
    "content": "Hi! I'm ready to help. What would you like to know?",
    "created_at": "2026-03-16T09:00:00Z"
  }
}
```

**curl example:**

```bash
curl -X POST "https://nexo.luzia.com/api/apps/YOUR_APP_ID/threads" \
  -H "X-App-Id: YOUR_APP_ID" \
  -H "X-App-Secret: YOUR_APP_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Morning briefing",
    "customer_id": "user_001"
  }'
```

### GET /apps/{app_id}/threads

List threads for an app, with optional filtering.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `customer_id` | string | Filter to threads belonging to this user. |
| `status` | string | Filter by status: `active`, `archived`. Default: all. |
| `limit` | int | Page size. Default: 20, max: 100. |
| `cursor` | string | Cursor from a previous response for pagination. |

**Response:**

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "app_id": "app_uuid",
      "title": "Morning briefing",
      "customer_id": "user_001",
      "status": "active",
      "created_at": "2026-03-16T09:00:00Z",
      "updated_at": "2026-03-16T09:15:00Z"
    }
  ],
  "next_cursor": "dGhyZWFkXzE2MA=="
}
```

Pass `next_cursor` as the `cursor` query parameter on the next request to fetch the following page. A `null` `next_cursor` means you are on the last page.

### POST /apps/{app_id}/threads/{thread_id}/messages

Send a user message into a thread. Nexo routes it to your webhook and stores the assistant response.

**Request body:**

```json
{
  "content": "What is today's top story?"
}
```

**Response** (the stored user message):

```json
{
  "id": "msg_uuid",
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "seq": 3,
  "role": "user",
  "content": "What is today's top story?",
  "content_json": {},
  "created_at": "2026-03-16T09:20:00Z"
}
```

**curl example:**

```bash
curl -X POST "https://nexo.luzia.com/api/apps/YOUR_APP_ID/threads/THREAD_ID/messages" \
  -H "X-App-Id: YOUR_APP_ID" \
  -H "X-App-Secret: YOUR_APP_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"content": "What is today'\''s top story?"}'
```

### GET /apps/{app_id}/threads/{thread_id}/messages

Fetch messages in a thread, newest first.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `before_seq` | int | Return only messages with `seq` less than this value. Use for pagination. |
| `limit` | int | Page size. Default: 20, max: 200. |

**Response** (array of message objects, newest first):

```json
[
  {
    "id": "msg_uuid_2",
    "thread_id": "550e8400-e29b-41d4-a716-446655440000",
    "seq": 4,
    "role": "assistant",
    "content": "The top story today is...",
    "content_json": {
      "source": "webhook",
      "cards": [],
      "actions": []
    },
    "created_at": "2026-03-16T09:20:05Z"
  },
  {
    "id": "msg_uuid_1",
    "thread_id": "550e8400-e29b-41d4-a716-446655440000",
    "seq": 3,
    "role": "user",
    "content": "What is today's top story?",
    "content_json": {},
    "created_at": "2026-03-16T09:20:00Z"
  }
]
```

To paginate backwards, pass the lowest `seq` from the current page as `before_seq` on your next request.

### POST /apps/{app_id}/threads/{thread_id}/messages/assistant

Inject an assistant message directly into a thread without triggering a webhook call. Use this when your backend has already determined what to say and you want to write it into the thread (for example, from a background job or push event follow-up).

**Request body:**

```json
{
  "content": "Here is your morning briefing for Monday, 17 March.",
  "content_parts": [
    { "type": "text", "text": "Here is your morning briefing for Monday, 17 March." }
  ],
  "metadata": {
    "prompt_suggestions": ["Tell me more", "Skip to headlines"]
  }
}
```

**Response:** the stored assistant message object (same shape as `MessageRead` above).

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

- Luzia Nexo: [nexo.luzia.com](https://nexo.luzia.com)
- Support: use the partner portal support flow at [nexo.luzia.com](https://nexo.luzia.com)
