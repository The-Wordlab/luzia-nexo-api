# Food Ordering Webhook

A standalone FastAPI webhook example for the Nexo Partner Agent API demonstrating a deeper food-commerce flow: restaurant discovery, dietary-aware menu filtering, basket building, checkout approval, delivery tracking, and reorder.

## Capabilities

| Intent | Trigger phrases | State |
|---|---|---|
| `menu_browse` | "show me the menu", "what's available", "vegan options" | simulated |
| `order_build` | "I want to order", "add to cart", "confirm order" | simulated |
| `order_track` | "track my order", "where is my delivery", "ETA" | simulated |

All capabilities are simulated - no real restaurant API or payment integration required.

## Optional profile context

This example now reads optional consent-scoped profile fields defensively:

- `profile.display_name` for greeting
- `profile.preferences.dietary` or `profile.dietary_restrictions` to bias menu browse results
- `profile.preferences.budget` to bias draft order composition
- `profile.preferences.cuisine` to bias the restaurant shortlist
- `profile.city` / `profile.country` to provide a delivery-area hint

If those attributes are absent, the webhook falls back to generic behavior.
Responses also include `metadata.personalization` describing which profile
inputs were actually used.

## Running locally

```bash
pip install -r requirements.txt

# Production-style default (Vertex via ADC)
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export GOOGLE_CLOUD_LOCATION=europe-west1

# Without auth
uvicorn app:app --reload --port 8095

# With HMAC auth
WEBHOOK_SECRET=my-secret uvicorn app:app --reload --port 8095
```

## Running with Docker

```bash
docker build -t food-ordering-webhook .
docker run -p 8095:8095 food-ordering-webhook
```

## Running tests

```bash
pip install -r requirements.txt
pytest -v
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_SECRET` | `""` | HMAC signing secret (optional) |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | litellm model identifier |
| `STREAMING_ENABLED` | `true` | Enable SSE streaming |

## API endpoints

- `GET /` - Service discovery
- `GET /.well-known/agent.json` - A2A-style capability discovery card
- `GET /health` - Health check
- `POST /` - Main Nexo webhook endpoint (JSON or SSE)
- `POST /ingest` - Reserved for future menu/order data ingestion

## Response envelope

```json
{
  "schema_version": "2026-03",
  "status": "completed",
  "task": {"id": "task_food_menu_browse", "status": "completed"},
  "capability": {"name": "food.ordering", "version": "1"},
  "content_parts": [{"type": "text", "text": "..."}],
  "artifacts": [],
  "cards": [
    {
      "type": "restaurant_shortlist",
      "title": "Nearby Delivery Options",
      "fields": [...]
    },
    {
      "type": "menu",
      "title": "Today's Menu",
      "fields": [...],
      "metadata": {"capability_state": "simulated"}
    }
  ],
  "actions": [
    {"type": "primary", "label": "Build My Order", "action": "build_order"}
  ]
}
```

## Card types

- **`restaurant_shortlist`** - Nearby or preference-aware delivery partner shortlist
- **`menu`** - Browsable list of items with price and dietary labels
- **`order_summary`** - Items in cart, total, notes, and checkout package
- **`order_status`** - Simulated delivery tracking (preparing / on-the-way / delivered)
