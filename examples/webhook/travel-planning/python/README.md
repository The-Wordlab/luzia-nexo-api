# Travel Planning Webhook

Multi-step travel flagship orchestration demo for the Nexo Partner Agent API.

Demonstrates the full travel lifecycle with simulated data - no real travel API required.

## Optional profile context

This example reads optional consent-scoped travel hints:

- `profile.display_name` for greeting
- `profile.preferences.budget` to choose a default trip budget tier when the
  user message does not specify one
- `profile.locale` and `profile.country` are preserved in response
  personalization metadata for future proof/debug surfaces

If these fields are absent, the webhook falls back to the generic mid-range
planning path. Responses include `metadata.personalization` so Nexo can show
which profile context was applied.

## Intents

| Intent | Trigger keywords | Returns |
|---|---|---|
| `trip_plan` | plan, trip, travel, destination, itinerary | Destination card with itinerary + budget breakdown |
| `flight_compare` | compare flights, price watch, direct flight | Flight shortlist card |
| `booking_handoff` | book now, ready to book, handoff | Connector-ready booking package |
| `budget_check` | budget, cost, spent, expense, how much | Expense tracking card with spent vs budget |
| `disruption_replan` | delay, cancelled, rebook, reroute, refund | Disruption alert card + alternative options |

## Running locally

```bash
pip install -r requirements.txt

# Production-style default (Vertex via ADC)
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export GOOGLE_CLOUD_LOCATION=europe-west1

uvicorn app:app --port 8096
```

Or with Docker:

```bash
docker build -t travel-planning .
docker run -p 8096:8096 travel-planning
```

## Running tests

```bash
pytest -q
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_SECRET` | `""` | HMAC secret for request signing (optional) |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | LiteLLM model identifier |
| `STREAMING_ENABLED` | `true` | Enable SSE streaming responses |

## Endpoints

- `GET /` - Service discovery
- `GET /.well-known/agent.json` - A2A-style capability discovery card
- `GET /health` - Health check
- `POST /` - Main webhook endpoint (JSON or SSE)
- `POST /ingest` - Placeholder for future data ingestion

## Example request

```bash
curl -X POST http://localhost:8096/ \
  -H "Content-Type: application/json" \
  -d '{
    "event": "message_created",
    "message": {"role": "user", "content": "Plan a 7-day trip to Barcelona"},
    "profile": {"display_name": "Sara"}
  }'
```

## Card types returned

- `trip_plan` - Destination + itinerary + estimated budget breakdown
- `flight_compare` - Flight shortlist tuned to the requested or saved budget tier
- `booking_handoff` - Connector-ready travel package with next-step approvals
- `budget_check` - Expense tracking card with spent vs budget, saving tips
- `disruption_alert` - Flight disruption alert with alternative options and approval actions

All cards include `metadata.capability_state: "simulated"`.
Streaming includes A2A task events: `task.started`, `task.delta`, `task.artifact`, and `done`.
