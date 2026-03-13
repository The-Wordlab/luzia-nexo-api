# Travel RAG Partner Webhook

A retrieval-augmented generation (RAG) travel assistant webhook for Nexo. Indexes 12 destination profiles and travel blog RSS feeds into pgvector, then answers user questions with rich destination cards.

## Quick Start

```bash
pip install -r requirements.txt

# Production-aligned defaults (Gemini via ADC):
GOOGLE_CLOUD_PROJECT=<your-project-id> GOOGLE_CLOUD_LOCATION=<your-region> \
LLM_MODEL=vertex_ai/gemini-2.5-flash EMBEDDING_MODEL=vertex_ai/text-embedding-004 \
uvicorn server:app --port 8092
```

On startup the server seeds 12 destination profiles (Paris, Tokyo, Barcelona, NYC, Bali, Rome, London, Sydney, Marrakech, Reykjavik, Cape Town, Kyoto) and crawls travel RSS feeds.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Main Nexo webhook - RAG answer + destination cards |
| GET | `/.well-known/agent.json` | A2A-style capability discovery card |
| POST | `/ingest` | Trigger destination seed + RSS feed re-crawl |
| GET | `/health` | Liveness probe with index stats |

## Test the webhook

```bash
curl -X POST http://localhost:8092/ \
  -H "Content-Type: application/json" \
  -d '{"message":{"content":"What are the best destinations in Europe for food lovers?"}}'
```

## Features

- **Intent detection**: routes queries to destination, itinerary, budget, or weather prompts
- **Dual collections**: searches both destination profiles and travel articles
- **Rich cards**: destination cards with highlights, budget, best time, and tag badges
- **Itinerary cards**: auto-generates day-by-day plans from destination highlights
- **SSE streaming**: optional streaming mode via `STREAMING_ENABLED=true`
- **A2A task events**: streams include `task.started`, `task.delta`, `task.artifact`, and `done`
- **Personalisation**: greets users by name when profile.display_name is provided

## Docker

```bash
docker build -t nexo-travel-rag .
docker run -p 8092:8080 \
  -e GOOGLE_CLOUD_PROJECT=<your-project-id> \
  -e GOOGLE_CLOUD_LOCATION=<your-region> \
  -e LLM_MODEL=vertex_ai/gemini-2.5-flash \
  -e EMBEDDING_MODEL=vertex_ai/text-embedding-004 \
  nexo-travel-rag
```

Or use the shared Docker Compose from `examples/`:

```bash
cd examples && docker compose up travel-rag
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | litellm model string |
| `EMBEDDING_MODEL` | `vertex_ai/text-embedding-004` | Embedding model |
| `WEBHOOK_SECRET` | _(empty)_ | HMAC-SHA256 secret (skip if empty) |
| `TRAVEL_FEEDS` | _(built-in)_ | Comma-separated RSS URLs |
| `REFRESH_INTERVAL_MINUTES` | `60` | Background re-crawl interval |
| `STREAMING_ENABLED` | `false` | Enable SSE streaming |
| `TOP_K` | `4` | Chunks to retrieve per query |
| `VECTOR_STORE_BACKEND` | `pgvector` | Only supported vector backend for this example. |
| `VECTOR_STORE_DURABLE` | `true` | Keep `true` when using managed durable storage |
| `PGVECTOR_DSN` | _(empty)_ | Postgres DSN used by pgvector storage |
| `PGVECTOR_SCHEMA` | `rag_travel` | Schema for travel vectors and metadata |
