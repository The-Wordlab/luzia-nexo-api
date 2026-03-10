#!/usr/bin/env python3
"""
News-feed RAG webhook server.

Crawls RSS feeds, indexes article chunks in ChromaDB, and answers user
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
    LLM_MODEL                litellm model string. Default: ollama/llama3.2
    EMBEDDING_MODEL          litellm embedding model. Default: text-embedding-3-small
    WEBHOOK_SECRET           HMAC-SHA256 signing secret; skipped if empty
    REFRESH_INTERVAL_MINUTES How often the background loop re-crawls. Default: 30
    CHROMA_PERSIST_DIR       Where ChromaDB stores its files. Default: ./chroma_data
    OLLAMA_API_BASE          Ollama server URL. Default: http://localhost:11434
    OPENAI_API_KEY           Required when using an OpenAI embedding or LLM model
    TOP_K                    Number of chunks to retrieve per query. Default: 5
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import logging
import os
import textwrap
from typing import Any

import chromadb
import feedparser
import litellm
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

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

LLM_MODEL: str = os.environ.get("LLM_MODEL", "ollama/llama3.2")
EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")
REFRESH_INTERVAL_MINUTES: int = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "30"))
CHROMA_PERSIST_DIR: str = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
OLLAMA_API_BASE: str = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
TOP_K: int = int(os.environ.get("TOP_K", "5"))

_raw_feeds = os.environ.get("NEWS_FEEDS", "")
NEWS_FEEDS: list[str] = (
    [u.strip() for u in _raw_feeds.split(",") if u.strip()] or DEFAULT_FEEDS
)

# Configure litellm base URL for Ollama when requested
if LLM_MODEL.startswith("ollama/"):
    os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)

CHUNK_SIZE_CHARS: int = 2000   # ~500 tokens at 4 chars/token
CHUNK_OVERLAP_CHARS: int = 200
COLLECTION_NAME: str = "news_articles"

# ---------------------------------------------------------------------------
# ChromaDB state
# ---------------------------------------------------------------------------

_chroma_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None
_index_stats: dict[str, Any] = {
    "num_chunks": 0,
    "last_refresh": None,
    "feeds": NEWS_FEEDS,
}


def get_collection() -> chromadb.Collection:
    """Return (or lazily create) the shared ChromaDB collection."""
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
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
    """Produce a stable, ChromaDB-safe document ID from arbitrary text."""
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
    """Crawl all configured RSS feeds and upsert chunks into ChromaDB.

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
    """Embed *query* and return top_k most similar chunks from ChromaDB."""
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


def _empty_index_response() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [
            {
                "type": "text",
                "text": (
                    "I don't have enough news context to answer that right now. "
                    "The index may still be loading — try again in a moment."
                ),
            }
        ],
        "cards": [],
        "actions": [],
    }


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


@app.get("/")
async def root() -> JSONResponse:
    """Service discovery endpoint for local/manual testing."""
    return JSONResponse(
        {
            "service": "webhook-news-rag-python",
            "description": "News RAG webhook using RSS ingestion, Chroma retrieval, and source cards.",
            "routes": [
                {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint"},
                {"path": "/ingest", "method": "POST", "description": "Trigger feed crawl + re-index"},
                {"path": "/health", "method": "GET", "description": "Index and model health details"},
            ],
            "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
            "schema_version": "2026-03-01",
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
async def receive_webhook(request: Request) -> JSONResponse:
    """Main webhook endpoint.

    Receives the standard Nexo webhook payload, retrieves relevant news
    chunks from ChromaDB, prompts the LLM, and returns a rich response
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

    if not user_text:
        return JSONResponse(
            {
                "schema_version": "2026-03-01",
                "status": "completed",
                "content_parts": [
                    {
                        "type": "text",
                        "text": "Please ask me a question about the latest news.",
                    }
                ],
                "cards": [],
                "actions": [],
            }
        )

    hits = await retrieve(user_text)

    if not hits:
        return JSONResponse(_empty_index_response())

    messages = build_rag_prompt(hits, user_text)
    try:
        answer = await ask_llm(messages)
    except Exception:
        logger.exception("LLM call failed")
        answer = (
            "I found relevant news articles but couldn't generate a response right now. "
            "Please try again."
        )

    return JSONResponse(
        {
            "schema_version": "2026-03-01",
            "status": "completed",
            "content_parts": [{"type": "text", "text": answer}],
            "cards": build_source_cards(hits),
            "actions": build_read_actions(hits),
        }
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
        }
    )
