# Travel Planner Webhook

Webhook-backed travel compatibility example for Nexo.

Use this example when you want a narrower booking-oriented slice. For the main flagship travel story, use `travel-planning`.

## Intents

| Intent | Prompt examples | Output |
|---|---|---|
| `itinerary` | "Plan a romantic weekend in Barcelona" | Itinerary card + actions |
| `flight_compare` | "Compare flights to Lisbon next month" | Flight options card |
| `booking_handoff` | "Prepare booking handoff for my Barcelona trip" | Connector handoff card |

Run locally:

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8098
```

Discovery metadata marks this example as:
- `showcase_family: travel`
- `showcase_role: secondary`
- `superseded_by: travel-planning`
