# Daily Routines Webhook

A Nexo partner webhook that demonstrates multi-step orchestration for daily productivity. Handles three intents with structured response cards.

## Capabilities

| Intent | Trigger keywords | Card type | Capability state |
|---|---|---|---|
| Morning briefing | morning, briefing, good morning, start my day | `morning_briefing` | Simulated |
| Schedule management | schedule, calendar, meeting, appointment | `schedule` | Simulated |
| Follow-up / reminders | reminder, remind, follow up, action item, todo | `action_items` | Simulated |

> **Simulated** — calendar, weather, and task data are seeded placeholders. No real calendar or weather APIs are called. Connect your own APIs to promote these to `live`.

## Optional profile context

This example supports optional consent-scoped context without requiring it:

- `profile.display_name` for greeting
- `profile.locale` to shape greeting/tone
- `profile.preferences.*` and `profile.facts` to create a visible "Personal focus"
  hint in the morning briefing

If those fields are missing, the webhook returns the generic seeded briefing.
Responses include `metadata.personalization` so Nexo can surface what context
was used.

## Run locally

```bash
# Install dependencies
pip install -r requirements.txt

# Production-style default (Vertex via ADC)
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export GOOGLE_CLOUD_LOCATION=europe-west1

# Optional: set webhook signature secret
export WEBHOOK_SECRET=your-secret

# Start the server
uvicorn app:app --reload --port 8094
```

The service starts at `http://localhost:8094`.

## Run with Docker

```bash
docker build -t routines-webhook .
docker run -p 8094:8094 \
  -e GOOGLE_CLOUD_PROJECT=your-gcp-project \
  -e GOOGLE_CLOUD_LOCATION=europe-west1 \
  routines-webhook
```

## Run tests

```bash
pytest test_routines.py -v
```

All tests are self-contained and mock LLM calls — no API key required.

## Example request

```bash
curl -X POST http://localhost:8094/ \
  -H "Content-Type: application/json" \
  -d '{
    "event": "message_created",
    "app": {},
    "thread": {},
    "message": {"role": "user", "content": "Good morning, what is my briefing?"},
    "profile": {"display_name": "Mark"}
  }'
```

### Example response

```json
{
  "schema_version": "2026-03",
  "status": "completed",
  "content_parts": [{"type": "text", "text": "Hey Mark! ..."}],
  "cards": [
    {
      "type": "morning_briefing",
      "title": "Good morning, Mark!",
      "subtitle": "Your daily overview",
      "badges": ["Daily Routines", "Simulated"],
      "fields": [
        {"label": "Weather", "value": "Partly cloudy, 18°C / 64°F"},
        {"label": "Meetings today", "value": "4 scheduled (09:00–17:00)"},
        {"label": "Top priorities", "value": "#1 Review pull request ... · #2 Prepare slides ..."}
      ],
      "metadata": {"capability_state": "simulated"}
    }
  ],
  "actions": [
    {"type": "primary", "label": "View Schedule", "action": "show_schedule"},
    {"type": "secondary", "label": "Set a Reminder", "action": "show_reminders"}
  ]
}
```

## SSE streaming

Include `Accept: text/event-stream` to receive a streaming response. The final `done` event carries `cards`, `actions`, and `schema_version`.
Streaming also includes A2A task events: `task.started`, `task.delta`, `task.artifact`, and `done`.

## Capability discovery

`GET /.well-known/agent.json` publishes A2A-style capability metadata for this example.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_SECRET` | _(empty)_ | HMAC secret for `X-Timestamp` + `X-Signature` verification |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | litellm model string |
| `STREAMING_ENABLED` | `true` | Enable SSE streaming when `Accept: text/event-stream` |

## Deploy to Cloud Run

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/routines-webhook
gcloud run deploy routines-webhook \
  --image gcr.io/YOUR_PROJECT/routines-webhook \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars LLM_MODEL=vertex_ai/gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT,GOOGLE_CLOUD_LOCATION=europe-west1
```
