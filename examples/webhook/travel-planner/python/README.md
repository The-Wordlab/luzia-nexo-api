# Travel Planner Webhook

Webhook-backed travel planning example for Nexo.

## Intents

| Intent | Prompt examples | Output |
|---|---|---|
| `itinerary` | "Plan a romantic weekend in Barcelona" | Itinerary card + actions |
| `flight_compare` | "Compare flights to Lisbon next month" | Flight options card |
| `booking_handoff` | "Book this plan" | Connector handoff card |

Run locally:

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8098
```
