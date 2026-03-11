# Football Live — Real-Time RAG Webhook

A production-quality webhook example for the Nexo Partner Agent API. Fetches live scores, standings, and top scorers from **football-data.org** for 3 leagues, stores them in ChromaDB for vector search, and answers user questions via RAG + LLM.

## Leagues

| Code | League |
|------|--------|
| PL | Premier League |
| PD | La Liga |
| BSA | Brasileirão |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (no API key needed — all mocked)
pytest test_football_live.py -v

# Start with seed data only (no API key needed)
uvicorn server:app --port 8003

# Start with live data
FOOTBALL_DATA_API_KEY=your_key uvicorn server:app --port 8003
```

## Intents

The webhook detects 4 intents from user messages:

| Intent | Example | Response |
|--------|---------|----------|
| scores | "Arsenal score" | Match results + score cards |
| standings | "La Liga table" | League table + standings card |
| scorers | "Top scorer?" | Top scorers + stats card |
| general | "Tell me about football" | Mixed context from all collections |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Main webhook (scores, standings, scorers) |
| GET | `/health` | Health check with collection counts |
| GET | `/admin/status` | Admin status (leagues, config) |
| POST | `/admin/refresh` | Trigger full data refresh |
| POST | `/ingest` | Full ingest (all leagues, all endpoints) |
| POST | `/ingest/live` | Live-only ingest (matches in play) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FOOTBALL_DATA_API_KEY` | (empty) | football-data.org API key |
| `WEBHOOK_SECRET` | (empty) | HMAC secret for signature verification |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | LiteLLM model identifier (production default via ADC) |
| `EMBEDDING_MODEL` | `vertex_ai/text-embedding-004` | LiteLLM embedding model (production default via ADC) |
| `STREAMING_ENABLED` | `true` | Enable SSE streaming |
| `REFRESH_INTERVAL` | `300` | Background refresh interval (seconds) |
| `TOP_K` | `5` | Number of search results per query |
| `CHROMA_PERSIST_DIR` | `./chroma_football_live` | ChromaDB persistence path |
| `VECTOR_STORE_BACKEND` | `chroma` | Vector backend label for health reporting (`chroma`, `vertex`, `pgvector`, ...) |
| `VECTOR_STORE_DURABLE` | `false` | Set `true` when backing vectors with durable managed storage |

## Architecture

```
User (Nexo) --> POST / --> detect_intent(message)
                                |
                 ┌──────────────┼──────────────┐
                 v              v              v
            "scores"      "standings"     "scorers"
                 |              |              |
            ChromaDB        ChromaDB       ChromaDB
                 |              |              |
                 └──────┬───────┘──────────────┘
                        v
                 LLM (context + prompt)
                        v
                 { content_parts, cards, actions }
```

Background refresh: football-data.org API → ChromaDB every 5 minutes.

## Docker

```bash
docker build -t football-live .
docker run -p 8003:8003 -e FOOTBALL_DATA_API_KEY=your_key football-live
```

## Testing

```bash
# All tests
pytest test_football_live.py -v

# Test specific intent
curl -X POST localhost:8003/ \
  -H "Content-Type: application/json" \
  -d '{"message":{"content":"Arsenal score"}}'

curl -X POST localhost:8003/ \
  -H "Content-Type: application/json" \
  -d '{"message":{"content":"La Liga table"}}'

curl -X POST localhost:8003/ \
  -H "Content-Type: application/json" \
  -d '{"message":{"content":"Who is top scorer?"}}'
```

## Seed Data

The webhook ships with realistic seed data (15 matches, 30 standings, 15 scorers across 3 leagues) so it works without an API key. Seed data is loaded automatically on startup if collections are empty.
