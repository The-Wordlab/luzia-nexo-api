# Sports-Feed RAG Partner Webhook

A football/soccer retrieval-augmented generation (RAG) partner webhook for Nexo.
It indexes live RSS feeds and structured match results into pgvector, then answers
user questions about scores, standings, and news using an LLM with retrieved context.

This is the full-featured variant of the sports-rag example. It splits ingestion into
a dedicated `ingest.py` module and provides the complete set of endpoints required
for a production partner integration, including SSE streaming and Cloud Run deployment.

## What it demonstrates

- Three vector collections: `articles` (RSS news), `match_results` (structured scores), `standings` (league tables)
- Intent detection: routes queries to the right collection (scores vs standings vs news)
- Structured cards in the Nexo response envelope: `match_result`, `standings_table`, `news_article`
- Actions: "View match details" deep links and "See full standings" links
- HMAC-SHA256 signature verification
- SSE streaming with `delta` + `done` events (enable via `STREAMING_ENABLED=true`)
- Separate `POST /ingest` (full crawl) and `POST /ingest/live` (lightweight, scores only) endpoints
- Optional live match data from [football-data.org](https://www.football-data.org/) API
- Demo-ready seed data: 10 results across Premier League, La Liga, Bundesliga, Serie A, Ligue 1
- Cloud Run deployment via `cloudbuild.yaml`

## Quick start

```bash
cd examples/webhook/sports-rag/python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Production-aligned config (Gemini via ADC)
export GOOGLE_CLOUD_PROJECT=<your-project-id>
export GOOGLE_CLOUD_LOCATION=<your-region>
export LLM_MODEL=vertex_ai/gemini-2.5-flash
export EMBEDDING_MODEL=vertex_ai/text-embedding-004

# Start the server
uvicorn server:app --reload --port 8002
```

The server seeds match data on startup. The demo works immediately even if RSS feeds are
unreachable, because the match seed data is hardcoded.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_SECRET` | *(empty)* | HMAC secret for Nexo request verification. Leave empty to skip during dev. |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` | litellm model string. Production default uses ADC. |
| `EMBEDDING_MODEL` | `vertex_ai/text-embedding-004` | Embedding model. Production default uses ADC. |
| `SPORT_FEEDS` | BBC Sport, ESPN FC, Sky Sports | Comma-separated RSS feed URLs to crawl. |
| `FOOTBALL_DATA_API_KEY` | *(empty)* | [football-data.org](https://www.football-data.org/) API key. Leave empty to use seed data. |
| `FOOTBALL_DATA_COMPETITION` | `PL` | Comma-separated competition codes, e.g. `PL,BL1,PD,SA,FL1`. |
| `REFRESH_INTERVAL_MINUTES` | `15` | Background refresh cadence (minutes). |
| `STREAMING_ENABLED` | `false` | Set to `true` to enable SSE streaming on `POST /`. |
| `VECTOR_STORE_BACKEND` | `pgvector` | Only supported vector backend for this example. |
| `VECTOR_STORE_DURABLE` | `true` | Keep `true` when using managed durable storage. |
| `PGVECTOR_DSN` | _(empty)_ | Postgres DSN used by pgvector storage. |
| `PGVECTOR_SCHEMA` | `rag_sports` | Schema for sports vectors and metadata |

## Endpoints

### `GET /.well-known/agent.json`

Publishes A2A-style capability metadata for discovery and contract introspection.

### `POST /`

The main Nexo webhook endpoint. Accepts the standard Nexo payload envelope.

Optionally streams via SSE when `Accept: text/event-stream` is present and
`STREAMING_ENABLED=true`.

**Example request (JSON):**
```json
{
  "event": "message.created",
  "message": {"content": "What was the Arsenal result this weekend?"},
  "profile": {"display_name": "Alex"}
}
```

**Example response (scores intent):**
```json
{
  "schema_version": "2026-03-01",
  "status": "completed",
  "content_parts": [
    {"type": "text", "text": "Hey Alex! Arsenal beat Chelsea 3-1 at the Emirates..."}
  ],
  "cards": [
    {
      "type": "match_result",
      "title": "Arsenal 3-1 Chelsea",
      "subtitle": "Premier League - Matchday 28",
      "description": "Goals: Saka 12', Havertz 45', Rice 67' - Palmer 55'",
      "badges": ["Premier League", "Full Time"],
      "fields": [
        {"label": "Date", "value": "March 5, 2026"},
        {"label": "Venue", "value": "Emirates Stadium"},
        {"label": "Goals", "value": "Saka 12', Havertz 45', Rice 67' - Palmer 55'"}
      ],
      "metadata": {"capability_state": "live"}
    }
  ],
  "actions": [
    {
      "id": "view_match_1",
      "label": "View match details: Arsenal vs Chelsea",
      "url": "https://www.google.com/search?q=Arsenal+vs+Chelsea+Premier+League+result",
      "style": "secondary"
    }
  ]
}
```

**SSE streaming example:**
```bash
curl -X POST http://localhost:8002/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"message":{"content":"Arsenal result"}}'
```

SSE events emitted:
- `data: {"type": "delta", "text": "Arsenal..."}` — streamed tokens
- `data: {"type": "done", "schema_version": "2026-03-01", "status": "completed", "cards": [...], "actions": [...]}` — final event with structured data
- plus A2A task events: `task.started`, `task.delta`, `task.artifact`, and `done`

### `POST /ingest`

Trigger a full ingest: RSS feeds + live match results + standings.

```bash
curl -X POST http://localhost:8002/ingest
```

Returns:
```json
{
  "status": "ok",
  "summary": {
    "article_chunks": 120,
    "match_records": 10,
    "standings_docs": 1
  },
  "timestamp": "2026-03-07T12:00:00Z"
}
```

### `POST /ingest/live`

Lightweight ingest: only fetches live match results + standings (no RSS crawl).
Use this for frequent polling (e.g., every 5 minutes during live matches).

```bash
curl -X POST http://localhost:8002/ingest/live
```

### `GET /admin/status`

Returns index statistics and current configuration.

```bash
curl http://localhost:8002/admin/status
```

### `POST /admin/refresh`

Queues a full background re-ingest (same as `POST /ingest` but non-blocking).

```bash
curl -X POST http://localhost:8002/admin/refresh
```

## Card types

| Card type | Triggered by | Key fields |
|---|---|---|
| `match_result` | Scores queries | Score line, goals, date, venue |
| `standings_table` | Standings queries | Top 5 teams with points |
| `news_article` | News queries | Title, excerpt, source link |

## Actions

| Action | Triggered by | Link target |
|---|---|---|
| View match details | Scores queries (up to 3) | Google search for match result |
| See full standings | Standings queries | BBC Sport table page |
| Read article | News queries (up to 3) | Original article URL |

## football-data.org integration

Register for a free API key at [football-data.org](https://www.football-data.org/client/register)
and set `FOOTBALL_DATA_API_KEY`. The server will then fetch live results and standings
instead of using seed data.

Supported competition codes: `PL` (Premier League), `BL1` (Bundesliga), `PD` (La Liga),
`SA` (Serie A), `FL1` (Ligue 1), `CL` (Champions League).

## Running tests

```bash
cd examples/webhook/sports-rag/python
pytest test_sports_rag.py -v
```

Tests use monkeypatching: no live vector store, LLM, or network access required.

## Deploying to Cloud Run

Prerequisites:
- A GCP project with Cloud Run and Artifact Registry enabled
- Cloud Build connected to your repository

```bash
# One-shot deploy
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions \
    _PROJECT_ID=my-project,\
    _REGION=us-central1,\
    _SERVICE_NAME=nexo-sports-rag,\
    _AR_REPO=nexo-examples \
  .

# Create required secrets first
echo -n "your-webhook-secret" | gcloud secrets create WEBHOOK_SECRET --data-file=-
# Optional only for OpenAI override:
echo -n "your-fd-key" | gcloud secrets create FOOTBALL_DATA_API_KEY --data-file=-
```

See `cloudbuild.yaml` for full configuration options.

## Demo queries to try

**Scores / results:**
- "What was the Arsenal result?"
- "Did Liverpool win this week?"
- "El Clasico result"
- "Bayern Munich score"

**Standings:**
- "Who is top of the Premier League?"
- "Show me the league table"
- "Where is Arsenal in the standings?"

**News:**
- "Any transfer news?"
- "Latest injury updates"
- "What happened at the weekend in football?"
