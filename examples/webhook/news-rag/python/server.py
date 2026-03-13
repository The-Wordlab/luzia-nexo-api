#!/usr/bin/env python3
"""
News-feed RAG webhook server.

Crawls RSS feeds, indexes article chunks in pgvector, and answers user
questions by retrieving relevant chunks and calling an LLM via litellm.

Two modes are supported:

1. POST /          - main Nexo webhook endpoint: receives the standard
                     Nexo webhook payload, does RAG, and returns the
                     rich response envelope.

2. POST /ingest    - trigger a feed crawl + re-index on demand
                     (suitable for a cron job or Cloud Scheduler).

Additional admin endpoints:
   GET  /health    - liveness probe (returns {status: ok, chunks: N})

Webhook response envelope (canonical Nexo format):
    {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [{"type": "text", "text": "..."}],
        "cards":   [...],   # source attribution cards
        "actions": [...]    # "Read full article" links
    }

Environment variables:
    NEWS_FEEDS               Comma-separated RSS URLs (defaults below)
    LLM_MODEL                litellm model string. Default: vertex_ai/gemini-2.5-flash
    EMBEDDING_MODEL          litellm embedding model. Default: vertex_ai/text-embedding-004
    WEBHOOK_SECRET           HMAC-SHA256 signing secret; skipped if empty
    REFRESH_INTERVAL_MINUTES How often the background loop re-crawls. Default: 30
    OLLAMA_API_BASE          Ollama server URL. Default: http://localhost:11434
    GOOGLE_CLOUD_PROJECT     Optional source for Vertex project defaults
    GOOGLE_CLOUD_LOCATION    Optional source for Vertex region defaults
    VERTEXAI_PROJECT         Optional explicit project for Vertex AI via LiteLLM
    VERTEXAI_LOCATION        Optional explicit location for Vertex AI via LiteLLM
    TOP_K                    Number of chunks to retrieve per query. Default: 5
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import textwrap
from typing import Any

import feedparser
import litellm
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

try:
    import psycopg
except ImportError:
    psycopg = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_FEEDS: list[str] = [
    "http://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://apnews.com/rss",
]

def _configure_vertex_env_defaults() -> None:
    """Map common GCP env vars into LiteLLM Vertex vars when unset."""
    project = (
        os.environ.get("VERTEXAI_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
    )
    location = (
        os.environ.get("VERTEXAI_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GCP_REGION")
    )
    if project:
        os.environ.setdefault("VERTEXAI_PROJECT", project)
    if location:
        os.environ.setdefault("VERTEXAI_LOCATION", location)


_configure_vertex_env_defaults()

LLM_MODEL: str = os.environ.get("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")
WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")
REFRESH_INTERVAL_MINUTES: int = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "30"))
OLLAMA_API_BASE: str = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
TOP_K: int = int(os.environ.get("TOP_K", "5"))
VECTOR_STORE_BACKEND: str = os.environ.get("VECTOR_STORE_BACKEND", "pgvector").strip().lower()
if VECTOR_STORE_BACKEND != "pgvector":
    raise RuntimeError(
        "news-rag only supports VECTOR_STORE_BACKEND=pgvector. Remove any legacy vector-store override."
    )

_raw_feeds = os.environ.get("NEWS_FEEDS", "")
NEWS_FEEDS: list[str] = (
    [u.strip() for u in _raw_feeds.split(",") if u.strip()] or DEFAULT_FEEDS
)

CHUNK_SIZE_CHARS: int = 2000   # ~500 tokens at 4 chars/token
CHUNK_OVERLAP_CHARS: int = 200
COLLECTION_NAME: str = "news_articles"
SCHEMA_VERSION: str = "2026-03-01"
CAPABILITY_NAME: str = "news.search"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-news-rag",
    "description": "News RAG webhook example for headline search and summarization.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Search and summarize recent news with source attribution.",
                "supports_streaming": True,
                "supports_cancellation": False,
            }
        ]
    },
}

# ---------------------------------------------------------------------------
# Vector store state (pgvector only)
# ---------------------------------------------------------------------------

PGVECTOR_DSN: str = os.environ.get("PGVECTOR_DSN", "")
PGVECTOR_SCHEMA: str = os.environ.get("PGVECTOR_SCHEMA", "rag_news")

_pg_conn: psycopg.Connection | None = None
_collection: Any | None = None
_index_stats: dict[str, Any] = {
    "num_chunks": 0,
    "last_refresh": None,
    "feeds": NEWS_FEEDS,
}


def _vector_store_metadata() -> dict[str, Any]:
    """Return runtime vector-store metadata for health/debug endpoints."""
    is_cloud_run = bool(os.environ.get("K_SERVICE"))
    return {
        "backend": "pgvector",
        "durable": True,
        "is_cloud_run": is_cloud_run,
    }


def _sanitize_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", value).lower()


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def _pg_connection() -> psycopg.Connection:
    global _pg_conn
    if psycopg is None:
        raise RuntimeError("psycopg is required when VECTOR_STORE_BACKEND=pgvector")
    if _pg_conn is None:
        if not PGVECTOR_DSN:
            raise RuntimeError("PGVECTOR_DSN is required when VECTOR_STORE_BACKEND=pgvector")
        _pg_conn = psycopg.connect(PGVECTOR_DSN, autocommit=True)
    return _pg_conn


class _PgVectorCollection:
    def __init__(self, name: str) -> None:
        self.schema = _sanitize_identifier(PGVECTOR_SCHEMA)
        self.table = _sanitize_identifier(name)
        self._dim: int | None = None

    def _table_ref(self) -> str:
        return f'"{self.schema}"."{self.table}"'

    def _exists(self, conn: psycopg.Connection) -> bool:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"{self.schema}.{self.table}",))
            return cur.fetchone()[0] is not None

    def _ensure_table(self, dim: int) -> None:
        conn = _pg_connection()
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_ref()} (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    embedding VECTOR({dim}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        self._dim = dim

    def _drop_table(self) -> None:
        conn = _pg_connection()
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self._table_ref()}")

    @staticmethod
    def _is_dimension_mismatch(exc: Exception) -> bool:
        message = str(exc).lower()
        return "different vector dimensions" in message or (
            "expected" in message and "dimensions" in message
        )

    def count(self) -> int:
        conn = _pg_connection()
        if not self._exists(conn):
            return 0
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {self._table_ref()}")
            return int(cur.fetchone()[0])

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not embeddings:
            return
        dim = len(embeddings[0])
        if self._dim is None or self._dim != dim:
            self._ensure_table(dim)
        conn = _pg_connection()
        rows = [
            (ids[i], documents[i], _vector_literal(embeddings[i]), json.dumps(metadatas[i] or {}))
            for i in range(len(ids))
        ]
        with conn.cursor() as cur:
            try:
                cur.executemany(
                    f"""
                    INSERT INTO {self._table_ref()} (id, document, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    rows,
                )
            except Exception as exc:
                if not self._is_dimension_mismatch(exc):
                    raise
                logger.warning(
                    "Detected pgvector dimension mismatch for %s. Recreating table with dim=%s.",
                    self._table_ref(),
                    dim,
                )
                self._drop_table()
                self._ensure_table(dim)
                cur.executemany(
                    f"""
                    INSERT INTO {self._table_ref()} (id, document, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    rows,
                )

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        include: list[str] | None = None,
    ) -> dict[str, list[list[Any]]]:
        include = include or ["documents", "metadatas", "distances"]
        if not query_embeddings:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        conn = _pg_connection()
        if not self._exists(conn):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        qvec = _vector_literal(query_embeddings[0])
        with conn.cursor() as cur:
            try:
                cur.execute(
                    f"""
                    SELECT id, document, metadata, (embedding <=> %s::vector) AS distance
                    FROM {self._table_ref()}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qvec, qvec, n_results),
                )
            except Exception as exc:
                if not self._is_dimension_mismatch(exc):
                    raise
                dim = len(query_embeddings[0])
                logger.warning(
                    "Detected pgvector dimension mismatch for %s query. Recreating table with dim=%s.",
                    self._table_ref(),
                    dim,
                )
                self._drop_table()
                self._ensure_table(dim)
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
            rows = cur.fetchall()
        ids = [r[0] for r in rows]
        docs = [r[1] for r in rows]
        metas = [r[2] for r in rows]
        dists = [float(r[3]) for r in rows]
        result: dict[str, list[list[Any]]] = {"ids": [ids]}
        if "documents" in include:
            result["documents"] = [docs]
        if "metadatas" in include:
            result["metadatas"] = [metas]
        if "distances" in include:
            result["distances"] = [dists]
        return result


def get_collection() -> Any:
    """Return (or lazily create) the shared pgvector collection."""
    global _collection
    if _collection is not None:
        return _collection
    _collection = _PgVectorCollection(COLLECTION_NAME)
    return _collection


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def strip_html(html: str) -> str:
    """Remove HTML tags and return clean text."""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def chunk_text(text: str) -> list[str]:
    """Split *text* into overlapping fixed-size character chunks."""
    step = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE_CHARS
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks


def stable_id(text: str) -> str:
    """Produce a stable document ID from arbitrary text."""
    return hashlib.md5(text.encode()).hexdigest()  # noqa: S324


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings using litellm.aembedding."""
    response = await litellm.aembedding(model=EMBEDDING_MODEL, input=texts)
    return [item["embedding"] for item in response.data]


# ---------------------------------------------------------------------------
# Feed crawling and indexing  (also called by ingest.py)
# ---------------------------------------------------------------------------


async def crawl_and_index_feeds() -> dict[str, Any]:
    """Crawl all configured RSS feeds and upsert chunks into pgvector.

    Returns a summary dict with num_chunks and last_refresh.
    """
    col = get_collection()
    total_upserted = 0

    for feed_url in NEWS_FEEDS:
        logger.info("Crawling feed: %s", feed_url)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            logger.exception("Failed to parse feed: %s", feed_url)
            continue

        feed_title: str = parsed.feed.get("title", feed_url)
        entries = parsed.entries[:50]  # cap per feed to avoid huge batches

        for entry in entries:
            title: str = entry.get("title", "")
            link: str = entry.get("link", "")
            published: str = entry.get("published", "")

            # Prefer full content; fall back to summary
            content_html = "".join(
                c.get("value", "") for c in entry.get("content", [])
            )
            summary_html: str = entry.get("summary", "") or entry.get("description", "")
            body = strip_html(content_html) if content_html else strip_html(summary_html)

            full_text = f"{title}. {body}".strip()
            if not full_text:
                continue

            chunks = chunk_text(full_text)
            if not chunks:
                continue

            # Embed in batches of 32
            for batch_start in range(0, len(chunks), 32):
                batch = chunks[batch_start : batch_start + 32]
                try:
                    embeddings = await embed(batch)
                except Exception:
                    logger.exception("Embedding failed for article: %s", title)
                    continue

                ids = [
                    stable_id(f"{link}:{batch_start + i}")
                    for i in range(len(batch))
                ]
                metadatas = [
                    {
                        "title": title,
                        "link": link,
                        "feed": feed_title,
                        "published": published,
                        "excerpt": textwrap.shorten(chunk, width=200, placeholder="..."),
                    }
                    for chunk in batch
                ]
                col.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=batch,
                    metadatas=metadatas,
                )
                total_upserted += len(batch)

    num_chunks = col.count()
    last_refresh = datetime.datetime.utcnow().isoformat() + "Z"
    _index_stats["num_chunks"] = num_chunks
    _index_stats["last_refresh"] = last_refresh
    logger.info("Index refresh complete. Total chunks in index: %d", num_chunks)
    return {"num_chunks": num_chunks, "last_refresh": last_refresh}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def retrieve(query: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
    """Embed *query* and return top_k most similar chunks from pgvector."""
    col = get_collection()
    count = col.count()
    if count == 0:
        return []

    embeddings = await embed([query])
    results = col.query(
        query_embeddings=embeddings,
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        hits.append(
            {
                "text": doc,
                "title": meta.get("title", ""),
                "link": meta.get("link", ""),
                "feed": meta.get("feed", ""),
                "published": meta.get("published", ""),
                "excerpt": meta.get("excerpt", ""),
                "score": round(1.0 - float(distance), 4),
            }
        )
    # Sort by descending relevance score
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


# ---------------------------------------------------------------------------
# RAG: prompt construction and LLM call
# ---------------------------------------------------------------------------


def build_rag_prompt(
    context_chunks: list[dict[str, Any]], question: str
) -> list[dict[str, str]]:
    """Build the messages list for the LLM given retrieved chunks and a question."""
    context_text = "\n\n---\n\n".join(
        f"[{i + 1}] {chunk['title']} ({chunk['feed']})\n{chunk['text']}"
        for i, chunk in enumerate(context_chunks)
    )
    system = (
        "You are a helpful news assistant. Answer the user's question based only on "
        "the provided news article excerpts below. If the answer is not contained in "
        "the excerpts, say so clearly. Keep answers concise, factual, and cite the "
        "article numbers (e.g. [1], [2]) where you draw information from.\n\n"
        f"News context:\n{context_text}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


async def ask_llm(messages: list[dict[str, str]]) -> str:
    """Call the configured LLM and return the assistant reply text."""
    response = await litellm.acompletion(model=LLM_MODEL, messages=messages)
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# HMAC signature validation
# ---------------------------------------------------------------------------


def verify_signature(request: Request, raw_body: bytes) -> None:
    """Raise HTTP 401 if the request signature does not match.

    Validation is skipped when WEBHOOK_SECRET is empty, which allows
    local development without managing secrets.

    Expects headers:
        X-Timestamp  - Unix timestamp string sent by Nexo
        X-Signature  - "sha256=<hex>" computed over "<timestamp>.<body>"
    """
    if not WEBHOOK_SECRET:
        return

    timestamp = request.headers.get("x-timestamp", "")
    signature = request.headers.get("x-signature", "")
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing X-Timestamp or X-Signature header")

    signed_payload = f"{timestamp}.{raw_body.decode('utf-8', errors='replace')}"
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Response envelope helpers
# ---------------------------------------------------------------------------


def deduplicate_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique sources by link, keeping the highest-score chunk per article."""
    seen: dict[str, dict[str, Any]] = {}
    for hit in hits:
        link = hit["link"]
        if link not in seen or hit["score"] > seen[link]["score"]:
            seen[link] = hit
    return list(seen.values())


def build_source_cards(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build source attribution cards from the top unique articles."""
    unique = deduplicate_sources(hits)[:3]
    cards: list[dict[str, Any]] = []
    for hit in unique:
        subtitle = hit["feed"]
        published = hit.get("published", "")
        if published:
            subtitle += f" — {published[:16]}"
        cards.append(
            {
                "type": "source",
                "title": hit["title"] or "News Article",
                "subtitle": subtitle,
                "description": hit["excerpt"],
                "metadata": {
                    "capability_state": "live",
                    "url": hit["link"],
                },
            }
        )
    return cards


def build_read_actions(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build 'Read full article' link actions from the top unique articles."""
    unique = deduplicate_sources(hits)[:3]
    return [
        {
            "id": f"read_{i + 1}",
            "label": "Read full article",
            "url": hit["link"],
            "style": "secondary",
        }
        for i, hit in enumerate(unique)
        if hit.get("link")
    ]


def prompt_suggestions_for_query(query: str) -> list[str]:
    q = (query or "").lower()
    if any(k in q for k in ["ai", "tech", "startup", "openai", "gemini"]):
        return [
            "Summarize the latest AI and tech news",
            "What changed this week in AI?",
            "Give me the top 3 tech headlines with sources",
        ]
    if any(k in q for k in ["market", "economy", "inflation", "stock"]):
        return [
            "What are the key market headlines today?",
            "Summarize the latest economy updates",
            "What is driving sentiment in the markets this week?",
        ]
    return [
        "What are the top headlines today?",
        "Give me a quick global news briefing",
        "What should I know in the news right now?",
    ]


def _empty_index_response() -> dict[str, Any]:
    return _build_envelope(
        text=(
            "I don't have enough news context to answer that right now. "
            "The index may still be loading - try again in a moment."
        ),
        metadata={
            "prompt_suggestions": [
                "What are the top headlines today?",
                "Summarize the latest AI and tech news",
                "Give me a quick global news briefing",
            ]
        },
    )


def _build_envelope(
    *,
    text: str,
    cards: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    task_status: str = "completed",
    metadata: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical Nexo envelope with A2A-aligned fields."""
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "error" if task_status in {"failed", "canceled"} else "completed",
        "task": {"id": "task_news_search", "status": task_status},
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": cards or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "metadata": metadata or {},
    }
    if error is not None:
        envelope["error"] = error
    return envelope


# ---------------------------------------------------------------------------
# Background refresh loop
# ---------------------------------------------------------------------------


async def _refresh_loop() -> None:
    """Periodically re-crawl all configured feeds."""
    interval = REFRESH_INTERVAL_MINUTES * 60
    while True:
        await asyncio.sleep(interval)
        logger.info("Background refresh triggered (every %d min)", REFRESH_INTERVAL_MINUTES)
        try:
            await crawl_and_index_feeds()
        except Exception:
            logger.exception("Background refresh failed")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="nexo-news-rag-webhook",
    description="News-feed RAG partner webhook for Nexo",
    version="1.0.0",
)


@app.get("/.well-known/agent.json")
async def agent_card() -> JSONResponse:
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root() -> JSONResponse:
    """Service discovery endpoint for local/manual testing."""
    return JSONResponse(
        {
            "service": "webhook-news-rag-python",
            "description": "News RAG webhook using RSS ingestion, pgvector retrieval, and source cards.",
            "routes": [
                {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint"},
                {"path": "/ingest", "method": "POST", "description": "Trigger feed crawl + re-index"},
                {"path": "/health", "method": "GET", "description": "Index and model health details"},
            ],
            "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
            "schema_version": SCHEMA_VERSION,
        }
    )


@app.on_event("startup")
async def _startup() -> None:
    """Start the initial feed crawl and schedule periodic refreshes."""
    logger.info("Starting initial feed crawl...")
    asyncio.create_task(crawl_and_index_feeds())
    asyncio.create_task(_refresh_loop())


# ---------------------------------------------------------------------------
# POST /  — main Nexo webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/")
async def receive_webhook(request: Request):
    """Main webhook endpoint.

    Receives the standard Nexo webhook payload, retrieves relevant news
    chunks from pgvector, prompts the LLM, and returns a rich response
    envelope containing the answer, source cards, and read-more actions.

    Nexo sends:
        {
            "event": "message.created",
            "message": {"content": "..."},
            "profile": {"name": "...", "locale": "..."},
            "thread": {"id": "..."},
            "timestamp": "..."
        }
    """
    raw_body = await request.body()
    verify_signature(request, raw_body)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    message: dict[str, Any] = data.get("message") or {}
    user_text: str = message.get("content", "").strip()

    wants_stream = "text/event-stream" in request.headers.get("accept", "").lower()

    if not user_text:
        envelope = _build_envelope(
            text="Please ask me a question about the latest news.",
            metadata={"prompt_suggestions": prompt_suggestions_for_query("")},
        )
        if wants_stream:
            return _stream_envelope_response(envelope)
        return JSONResponse(envelope)

    hits = await retrieve(user_text)

    if not hits:
        envelope = _empty_index_response()
        if wants_stream:
            return _stream_envelope_response(envelope)
        return JSONResponse(envelope)

    messages = build_rag_prompt(hits, user_text)
    try:
        answer = await ask_llm(messages)
    except Exception:
        logger.exception("LLM call failed")
        answer = (
            "I found relevant news articles but couldn't generate a response right now. "
            "Please try again."
        )

    envelope = _build_envelope(
        text=answer,
        cards=build_source_cards(hits),
        actions=build_read_actions(hits),
        artifacts=[
            {
                "type": "application/json",
                "name": "news_hits",
                "data": [
                    {
                        "title": h.get("title"),
                        "url": h.get("link"),
                        "score": h.get("score"),
                    }
                    for h in deduplicate_sources(hits)[:5]
                ],
            }
        ],
        metadata={"prompt_suggestions": prompt_suggestions_for_query(user_text)},
    )
    if wants_stream:
        return _stream_envelope_response(envelope)
    return JSONResponse(envelope)


def _stream_envelope_response(envelope: dict[str, Any]) -> StreamingResponse:
    """Return a canonical SSE response with delta + done events."""
    text = " ".join(
        p.get("text", "")
        for p in (envelope.get("content_parts") or [])
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()

    async def stream():
        task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
        yield (
            "event: task.started\ndata: "
            + json.dumps({"task": {"id": task.get("id"), "status": "in_progress"}})
            + "\n\n"
        )
        if text:
            yield f'event: delta\ndata: {json.dumps({"text": text})}\n\n'
            yield (
                "event: task.delta\ndata: "
                + json.dumps({"text": text})
                + "\n\n"
            )
        for artifact in envelope.get("artifacts") or []:
            yield f"event: task.artifact\ndata: {json.dumps(artifact)}\n\n"
        yield f"event: done\ndata: {json.dumps(envelope)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /ingest  — on-demand feed crawl + index
# ---------------------------------------------------------------------------


@app.post("/ingest")
async def ingest(background_tasks: BackgroundTasks) -> JSONResponse:
    """Trigger a feed crawl and re-index in the background.

    Returns immediately; the crawl runs asynchronously. Use GET /health
    to check the updated chunk count after the crawl completes.

    Suitable for a cron job or Cloud Scheduler:
        POST /ingest  (no body required)
    """
    background_tasks.add_task(crawl_and_index_feeds)
    return JSONResponse({"status": "ingest_started", "feeds": NEWS_FEEDS})


# ---------------------------------------------------------------------------
# GET /health  — liveness probe
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    """Return current index stats for liveness/readiness checks."""
    col = get_collection()
    return JSONResponse(
        {
            "status": "ok",
            "chunks": col.count(),
            "last_refresh": _index_stats.get("last_refresh"),
            "feeds": _index_stats.get("feeds"),
            "llm_model": LLM_MODEL,
            "embedding_model": EMBEDDING_MODEL,
            "vector_store": _vector_store_metadata(),
        }
    )
