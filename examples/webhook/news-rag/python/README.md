# News-Feed RAG Webhook — Python

A FastAPI webhook server that answers user questions from live RSS news feeds using
Retrieval-Augmented Generation (RAG).

On startup the server crawls configured RSS feeds, chunks and embeds articles into a
pgvector index on Postgres, and then serves a
[Nexo](https://the-wordlab.github.io/luzia-nexo-api/) webhook endpoint. When a
question arrives it embeds the question, retrieves the top-5 matching chunks, builds
a grounded prompt, and calls an LLM via [litellm](https://docs.litellm.ai/) — enabling
zero-code switching between Ollama, OpenAI, or Vertex AI.

## What this demonstrates

- RSS feed crawling with `feedparser`
- Chunked article indexing in pgvector (Postgres-backed vector store)
- Query embedding and cosine-similarity retrieval (top-K chunks)
- RAG prompt construction grounded in retrieved news context
- Nexo webhook response envelope with `content_parts`, `cards`, and `actions`
- Source attribution cards with article titles, feed names, and publish dates
- "Read full article" link actions
- HMAC-SHA256 request signature validation
- Background re-indexing loop (configurable interval)
- Separate `/ingest` endpoint for cron-driven re-crawls
- Docker + Cloud Build/Cloud Run deployment

## Quick start

### 1. Install dependencies

```bash
cd examples/webhook/news-rag/python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
# HMAC validation — set to match the secret configured in your Nexo app
export WEBHOOK_SECRET=your_secret_here   # omit to skip validation locally

# ADC-first defaults (production-aligned)
export GOOGLE_CLOUD_PROJECT=<your-project-id>
export GOOGLE_CLOUD_LOCATION=<your-region>
export LLM_MODEL=vertex_ai/gemini-2.5-flash
export EMBEDDING_MODEL=vertex_ai/text-embedding-004

# Development override (OpenAI)
# export OPENAI_API_KEY=sk-...
# export LLM_MODEL=openai/gpt-4o-mini
# export EMBEDDING_MODEL=text-embedding-3-small

# Optional overrides
export NEWS_FEEDS="http://feeds.bbci.co.uk/news/rss.xml,https://techcrunch.com/feed/"
export REFRESH_INTERVAL_MINUTES=30
export VECTOR_STORE_BACKEND=pgvector
export VECTOR_STORE_DURABLE=true
export PGVECTOR_DSN=postgresql://postgres:postgres@localhost:55432/nexo_rag
export PGVECTOR_SCHEMA=rag_news
export TOP_K=5
```

### 3. Pre-populate the index (optional)

The server crawls feeds automatically on startup, but you can run the ingestion
script independently to pre-warm the index or test the crawl in isolation:

```bash
python ingest.py
```

### 4. Start the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8080
```

The server crawls feeds and builds the index on startup. First responses are available
once the initial crawl completes (typically 10-30 seconds).

### 5. Connect to Nexo

In your Nexo app configuration set the webhook URL to:

```
http://<your-host>:8080/
```

## LLM options

| Use case | `LLM_MODEL` | Notes |
|---|---|---|
| Production default | `vertex_ai/gemini-2.5-flash` | Uses ADC (`gcloud auth application-default login`) |
| OpenAI | `gpt-4o-mini` | Requires `OPENAI_API_KEY` |
| Local Ollama | `ollama/llama3.2` | Requires [Ollama](https://ollama.com) running |
| Any litellm provider | see [litellm docs](https://docs.litellm.ai/docs/providers) | Provider-agnostic |

## Embedding options

| Use case | `EMBEDDING_MODEL` | Notes |
|---|---|---|
| Production default | `vertex_ai/text-embedding-004` | Uses ADC (`gcloud auth application-default login`) |
| OpenAI | `text-embedding-3-small` | Requires `OPENAI_API_KEY` |
| Vertex AI | `vertex_ai/text-embedding-004` | Requires GCP auth |
| Ollama local | `ollama/nomic-embed-text` | Requires Ollama + `ollama pull nomic-embed-text` |

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/` | Main Nexo webhook — receives a message, does RAG, returns answer |
| `GET` | `/.well-known/agent.json` | A2A-style capability discovery card |
| `POST` | `/ingest` | Trigger an immediate re-crawl of all feeds (runs in background) |
| `GET` | `/health` | Liveness probe — returns index stats |

## Request format (Nexo sends this)

```json
{
  "event": "message.created",
  "message": {"content": "What is happening in tech news today?"},
  "profile": {"name": "Alice", "locale": "en"},
  "thread": {"id": "thread_abc"},
  "timestamp": "2026-03-07T12:00:00Z"
}
```

## Response format

```json
{
  "schema_version": "2026-03-01",
  "status": "completed",
  "content_parts": [
    {"type": "text", "text": "Based on [1] and [2], OpenAI released GPT-5 today..."}
  ],
  "cards": [
    {
      "type": "source",
      "title": "OpenAI releases GPT-5",
      "subtitle": "TechCrunch — 2026-03-07",
      "description": "OpenAI today announced GPT-5 with improved reasoning...",
      "metadata": {
        "capability_state": "live",
        "url": "https://techcrunch.com/..."
      }
    }
  ],
  "actions": [
    {
      "id": "read_1",
      "label": "Read full article",
      "url": "https://techcrunch.com/...",
      "style": "secondary"
    }
  ]
}
```

## Signature validation

When `WEBHOOK_SECRET` is set, the server validates every incoming request using
HMAC-SHA256. Nexo sends two headers:

| Header | Value |
|---|---|
| `X-Timestamp` | Unix timestamp string |
| `X-Signature` | `sha256=<hex>` — HMAC of `"<timestamp>.<raw_body>"` |

Validation is skipped when `WEBHOOK_SECRET` is empty, so local development requires
no secret configuration.

## Environment variable reference

| Variable | Default | Description |
|---|---|---|
| `NEWS_FEEDS` | BBC, Reuters, AP News | Comma-separated RSS URLs |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | litellm model string for completions |
| `EMBEDDING_MODEL` | `vertex_ai/text-embedding-004` | litellm model string for embeddings |
| `WEBHOOK_SECRET` | _(empty)_ | HMAC-SHA256 secret; verification skipped if empty |
| `REFRESH_INTERVAL_MINUTES` | `30` | How often the background loop re-crawls all feeds |
| `VECTOR_STORE_BACKEND` | `pgvector` | Vector backend label for health reporting (`pgvector`, `vertex`, ...) |
| `VECTOR_STORE_DURABLE` | `true` | Keep `true` for managed durable storage |
| `PGVECTOR_DSN` | _(empty)_ | Postgres DSN used when `VECTOR_STORE_BACKEND=pgvector` |
| `PGVECTOR_SCHEMA` | `rag_news` | Schema for news vectors and metadata |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Ollama server base URL |
| `OPENAI_API_KEY` | _(empty)_ | Required for OpenAI embeddings or completions |
| `TOP_K` | `5` | Number of chunks to retrieve per query |
| `PORT` | `8080` | HTTP port (used by Dockerfile CMD) |

## Running tests

```bash
pytest test_news_rag.py -v
```

All tests are self-contained — no API keys, no running Ollama, no network calls
required. External services are mocked.

## Docker

```bash
# Build
docker build -t nexo-news-rag .

# Run (production-like via ADC + Vertex)
docker run -p 8080:8080 \
  -e GOOGLE_CLOUD_PROJECT=<your-project-id> \
  -e GOOGLE_CLOUD_LOCATION=<your-region> \
  -e LLM_MODEL=vertex_ai/gemini-2.5-flash \
  -e EMBEDDING_MODEL=vertex_ai/text-embedding-004 \
  -e WEBHOOK_SECRET=your_secret \
  -e VECTOR_STORE_BACKEND=pgvector \
  -e VECTOR_STORE_DURABLE=true \
  -e PGVECTOR_DSN=postgresql://postgres:postgres@host.docker.internal:55432/nexo_rag \
  -e PGVECTOR_SCHEMA=rag_news \
  nexo-news-rag
```

## Cloud Run deployment

The included `cloudbuild.yaml` builds and deploys to Cloud Run. Before first deploy:

1. Create Secret Manager secrets:
   ```bash
   echo -n "your_webhook_secret" | gcloud secrets create webhook-secret --data-file=-
   # Optional only for OpenAI development override:
   # echo -n "sk-..." | gcloud secrets create OPENAI_API_KEY --data-file=-
   ```

2. Grant the Cloud Run service account access to both secrets.

3. Trigger a build:
   ```bash
   gcloud builds submit \
     --config=cloudbuild.yaml \
     --substitutions=_REGION=europe-west1,_SERVICE_NAME=nexo-news-rag \
     .
   ```

For persistent vectors on Cloud Run, use managed Postgres with pgvector by setting:
- `VECTOR_STORE_BACKEND=pgvector`
- `VECTOR_STORE_DURABLE=true`
- `PGVECTOR_DSN` from Secret Manager
- `PGVECTOR_SCHEMA=rag_news`

`GET /health` now includes a `vector_store` block showing backend and durability.
