# Travel Planning Webhook

Multi-step travel planning orchestration demo for the Nexo Partner Agent API.

Demonstrates 3 intents with simulated data - no real travel API required.

## Intents

| Intent | Trigger keywords | Returns |
|---|---|---|
| `trip_plan` | plan, trip, travel, destination, itinerary | Destination card with itinerary + budget breakdown |
| `budget_check` | budget, cost, spent, expense, how much | Expense tracking card with spent vs budget |
| `disruption_replan` | delay, cancelled, rebook, reroute, refund | Disruption alert card + alternative options |

## Running locally

```bash
pip install -r requirements.txt
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
| `LLM_MODEL` | `gpt-4o-mini` | LiteLLM model identifier |
| `STREAMING_ENABLED` | `true` | Enable SSE streaming responses |

## Endpoints

- `GET /` - Service discovery
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
- `budget_check` - Expense tracking card with spent vs budget, saving tips
- `disruption_alert` - Flight disruption alert with alternative options and approval actions

All cards include `metadata.capability_state: "simulated"`.
