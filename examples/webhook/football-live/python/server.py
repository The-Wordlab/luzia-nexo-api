"""Football Live — Real-Time RAG Webhook for Nexo Partner Agent API.

Covers 3 leagues: Premier League, La Liga, Brasileirão.
Uses ChromaDB vector search + LLM for RAG responses.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import litellm
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

import ingest as _ingest_module
from football_api import COMPETITIONS, FootballDataClient
from ingest import (
    COLLECTION_MATCHES,
    COLLECTION_SCORERS,
    COLLECTION_STANDINGS,
    embed_texts,
    get_collection,
    run_full_ingest,
    run_live_ingest,
    seed_matches,
    seed_scorers,
    seed_standings,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
STREAMING_ENABLED = os.environ.get("STREAMING_ENABLED", "true").lower() == "true"
REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL", "300"))  # 5 min default
TOP_K = int(os.environ.get("TOP_K", "5"))
VECTOR_STORE_BACKEND = os.environ.get("VECTOR_STORE_BACKEND", "chroma").strip().lower()
VECTOR_STORE_DURABLE_OVERRIDE = os.environ.get("VECTOR_STORE_DURABLE", "").strip().lower()

SCHEMA_VERSION = "2026-03-01"


def _vector_store_metadata() -> dict[str, Any]:
    """Return runtime vector-store metadata for health/debug endpoints."""
    backend = VECTOR_STORE_BACKEND or "chroma"
    if VECTOR_STORE_DURABLE_OVERRIDE in {"1", "true", "yes"}:
        durable = True
    elif VECTOR_STORE_DURABLE_OVERRIDE in {"0", "false", "no"}:
        durable = False
    else:
        durable = backend in {"vertex", "vertex-ai", "vertex-vector-search", "pgvector", "alloydb", "cloudsql"}

    is_cloud_run = bool(os.environ.get("K_SERVICE"))
    warning: str | None = None
    if is_cloud_run and backend == "chroma" and not durable:
        warning = "ChromaDB on Cloud Run uses instance-local disk. Use a managed vector backend for durable production state."

    return {
        "backend": backend,
        "durable": durable,
        "is_cloud_run": is_cloud_run,
        "chroma_persist_dir": _ingest_module.CHROMA_PERSIST_DIR if backend == "chroma" else None,
        "warning": warning,
    }

# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------


def _verify_signature(secret: str, raw_body: bytes, timestamp: str, signature: str) -> bool:
    if not secret or not timestamp or not signature:
        return False
    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = "sha256=" + hmac_mod.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac_mod.compare_digest(expected, signature)


def _require_signature(request: Request, raw_body: bytes) -> None:
    if not WEBHOOK_SECRET:
        return
    timestamp = request.headers.get("x-timestamp", "")
    signature = request.headers.get("x-signature", "")
    if not _verify_signature(WEBHOOK_SECRET, raw_body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "standings": ["table", "standings", "league table", "ranking", "position", "clasificación", "tabela"],
    "scorers": ["scorer", "scorers", "top scorer", "golden boot", "goals scored", "goleador", "artilheiro", "who scored the most"],
    "scores": ["score", "result", "match", "game", "live", "playing", "resultado", "placar"],
}


def detect_intent(message: str) -> str:
    """Detect user intent from message text via keyword counting.

    Priority: standings > scorers > scores > general.
    """
    text = message.lower()
    counts: dict[str, int] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        counts[intent] = sum(1 for kw in keywords if kw in text)

    # Priority order for tie-breaking
    for intent in ("standings", "scorers", "scores"):
        if counts.get(intent, 0) > 0:
            # Check if another intent has strictly more matches
            if all(counts[intent] >= counts.get(other, 0) for other in INTENT_KEYWORDS):
                return intent
            # If tied, priority order wins
            if counts[intent] > 0:
                return intent

    return "general"


# ---------------------------------------------------------------------------
# ChromaDB search helpers
# ---------------------------------------------------------------------------


def search_matches(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    collection = get_collection(COLLECTION_MATCHES)
    count = collection.count()
    if count == 0:
        return []
    embeddings = embed_texts([query])
    results = collection.query(
        query_embeddings=embeddings,
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )
    matches: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        matches.append({
            "id": results["ids"][0][i],
            "text": doc,
            "home_team": meta.get("home_team", ""),
            "away_team": meta.get("away_team", ""),
            "home_score": meta.get("home_score", 0),
            "away_score": meta.get("away_score", 0),
            "competition": meta.get("competition", ""),
            "competition_id": meta.get("competition_id", ""),
            "matchday": meta.get("matchday", 0),
            "date": meta.get("date", ""),
            "status": meta.get("status", ""),
            "goals": meta.get("goals", ""),
            "venue": meta.get("venue", ""),
            "live_minute": meta.get("live_minute", 0),
            "distance": results["distances"][0][i],
        })
    return matches


def search_standings(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    collection = get_collection(COLLECTION_STANDINGS)
    count = collection.count()
    if count == 0:
        return []
    embeddings = embed_texts([query])
    results = collection.query(
        query_embeddings=embeddings,
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )
    entries: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        entries.append({
            "id": results["ids"][0][i],
            "text": doc,
            "position": meta.get("position", 0),
            "team": meta.get("team", ""),
            "won": meta.get("won", 0),
            "drawn": meta.get("drawn", 0),
            "lost": meta.get("lost", 0),
            "gd": meta.get("gd", 0),
            "points": meta.get("points", 0),
            "competition": meta.get("competition", ""),
            "distance": results["distances"][0][i],
        })
    return entries


def search_scorers(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    collection = get_collection(COLLECTION_SCORERS)
    count = collection.count()
    if count == 0:
        return []
    embeddings = embed_texts([query])
    results = collection.query(
        query_embeddings=embeddings,
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )
    scorers: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        scorers.append({
            "id": results["ids"][0][i],
            "text": doc,
            "name": meta.get("name", ""),
            "team": meta.get("team", ""),
            "goals": meta.get("goals", 0),
            "penalties": meta.get("penalties", 0),
            "assists": meta.get("assists", 0),
            "played_matches": meta.get("played_matches", 0),
            "competition": meta.get("competition", ""),
            "distance": results["distances"][0][i],
        })
    return scorers


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


def match_to_card(match: dict[str, Any]) -> dict[str, Any]:
    """Convert a match dict to the Nexo card envelope format (live-aware)."""
    score_line = f"{match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}"
    subtitle = f"{match.get('competition', '')} — Matchday {match.get('matchday', '')}"

    # Status badge
    status = match.get("status", "FINISHED")
    if status == "IN_PLAY":
        minute = match.get("live_minute")
        badge = f"LIVE {minute}'" if minute else "LIVE"
    elif status == "SCHEDULED":
        badge = "Upcoming"
    else:
        badge = "Full Time"

    fields: list[dict[str, str]] = [
        {"label": "Date", "value": str(match.get("date", ""))},
    ]
    if match.get("venue"):
        fields.append({"label": "Venue", "value": match["venue"]})
    if match.get("goals"):
        fields.append({"label": "Goals", "value": match["goals"][:120]})

    badges = [match.get("competition", ""), badge]

    return {
        "type": "match_result",
        "title": score_line,
        "subtitle": subtitle,
        "description": f"Goals: {match['goals']}" if match.get("goals") else subtitle,
        "badges": badges,
        "fields": fields,
        "metadata": {"capability_state": "live"},
    }


def build_standings_card(
    standings: list[dict[str, Any]], competition: str
) -> dict[str, Any]:
    """Build a standings_table card with W/D/L detail."""
    top5 = standings[:5]
    return {
        "type": "standings_table",
        "title": f"{competition} Table",
        "subtitle": "Current Standings",
        "badges": [competition, "2025/26"],
        "fields": [
            {
                "label": f"{s.get('position', i + 1)}. {s.get('team', '')}",
                "value": f"W{s.get('won', 0)} D{s.get('drawn', 0)} L{s.get('lost', 0)} · {s.get('points', 0)} pts",
            }
            for i, s in enumerate(top5)
        ],
        "metadata": {"capability_state": "live"},
    }


def build_scorers_card(
    scorers: list[dict[str, Any]], competition: str
) -> dict[str, Any]:
    """Build a top_scorers card with penalties and assists."""
    top5 = scorers[:5]
    fields: list[dict[str, str]] = []
    for i, s in enumerate(top5):
        pen = f" ({s.get('penalties', 0)} pen)" if s.get("penalties") else ""
        assists = f" · {s.get('assists', 0)} assists" if s.get("assists") else ""
        fields.append({
            "label": f"{i + 1}. {s.get('name', '')} ({s.get('team', '')})",
            "value": f"{s.get('goals', 0)} goals{pen}{assists}",
        })
    return {
        "type": "top_scorers",
        "title": f"{competition} Top Scorers",
        "subtitle": "Golden Boot Race",
        "badges": [competition, "2025/26"],
        "fields": fields,
        "metadata": {"capability_state": "live"},
    }


# ---------------------------------------------------------------------------
# LLM streaming
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a football expert assistant. Answer questions about football matches, standings, and scorers using the provided context. Be concise, engaging, and accurate. If live matches are happening, highlight them. Always mention the competition name. Use the data provided — do not make up scores or statistics."""


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream LLM response tokens as SSE events."""
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=400,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                payload = json.dumps({"type": "delta", "text": delta})
                yield f"data: {payload}\n\n"
    except Exception as exc:
        logger.warning("LLM streaming failed: %s", exc)
        error_text = "I'm having trouble generating a response right now."
        payload = json.dumps({"type": "delta", "text": error_text})
        yield f"data: {payload}\n\n"


async def call_llm(system_prompt: str, user_message: str) -> str:
    """Non-streaming LLM call."""
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=400,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I'm having trouble generating a response right now."


# ---------------------------------------------------------------------------
# Personalisation
# ---------------------------------------------------------------------------


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile", {}) or {}
    name = profile.get("display_name") or profile.get("name") or ""
    return name.strip()


# ---------------------------------------------------------------------------
# Background refresh
# ---------------------------------------------------------------------------

_refresh_task: asyncio.Task | None = None


async def _background_refresh_loop() -> None:
    """Periodically refresh data from football-data.org."""
    if not FOOTBALL_DATA_API_KEY:
        logger.info("No FOOTBALL_DATA_API_KEY set; background refresh disabled")
        return
    client = FootballDataClient(FOOTBALL_DATA_API_KEY)
    cycle = 0
    while True:
        await asyncio.sleep(REFRESH_INTERVAL)
        try:
            cycle += 1
            if cycle % 6 == 0:  # Full ingest every 30 min
                await run_full_ingest(client)
                logger.info("Full ingest completed (cycle %d)", cycle)
            else:
                count = await run_live_ingest(client)
                logger.info("Live ingest: %d matches updated (cycle %d)", count, cycle)
        except Exception as exc:
            logger.warning("Background refresh failed: %s", exc)


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global _refresh_task
    logger.info("Football Live startup: seeding data...")
    seed_matches()
    seed_standings()
    seed_scorers()

    # Optional: initial full ingest if API key is set
    if FOOTBALL_DATA_API_KEY:
        try:
            client = FootballDataClient(FOOTBALL_DATA_API_KEY)
            totals = await run_full_ingest(client)
            logger.info("Initial ingest: %s", totals)
        except Exception as exc:
            logger.warning("Initial ingest failed (using seed data): %s", exc)

    _refresh_task = asyncio.create_task(_background_refresh_loop())

    logger.info(
        "Football Live ready. Collections: matches=%d standings=%d scorers=%d",
        get_collection(COLLECTION_MATCHES).count(),
        get_collection(COLLECTION_STANDINGS).count(),
        get_collection(COLLECTION_SCORERS).count(),
    )
    yield
    if _refresh_task:
        _refresh_task.cancel()


app = FastAPI(title="Football Live Webhook", lifespan=lifespan)


@app.get("/")
async def root():
    """Service discovery endpoint for local/manual testing."""
    return {
        "service": "webhook-football-live-python",
        "description": "Live football webhook with matches, standings, scorers, and optional SSE output.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/health", "method": "GET", "description": "Collection counts and timestamp"},
            {"path": "/admin/status", "method": "GET", "description": "Admin status and config"},
            {"path": "/admin/refresh", "method": "POST", "description": "Run full refresh from football-data.org"},
            {"path": "/ingest", "method": "POST", "description": "Run full ingest"},
            {"path": "/ingest/live", "method": "POST", "description": "Run live matches ingest"},
        ],
        "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature) on webhook path",
        "schema_version": SCHEMA_VERSION,
    }


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/")
async def webhook(request: Request):
    raw_body = await request.body()
    _require_signature(request, raw_body)

    data = json.loads(raw_body)
    message = data.get("message", {})
    query = message.get("content", "")
    if not query:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    intent = detect_intent(query)
    display_name = _get_display_name(data)

    # Build context and cards based on intent
    context_parts: list[str] = []
    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    if intent == "standings":
        results = search_standings(query, n_results=TOP_K)
        if results:
            context_parts = [r["text"] for r in results]
            # Group by competition for cards
            seen_comps: set[str] = set()
            for r in results:
                comp = r.get("competition", "")
                if comp and comp not in seen_comps:
                    seen_comps.add(comp)
                    comp_results = [x for x in results if x.get("competition") == comp]
                    cards.append(build_standings_card(comp_results, comp))
            actions = [{"type": "primary", "label": "Full Table", "url": "https://www.google.com/search?q=" + query.replace(" ", "+")}]

    elif intent == "scorers":
        results = search_scorers(query, n_results=TOP_K)
        if results:
            context_parts = [r["text"] for r in results]
            seen_comps: set[str] = set()
            for r in results:
                comp = r.get("competition", "")
                if comp and comp not in seen_comps:
                    seen_comps.add(comp)
                    comp_results = [x for x in results if x.get("competition") == comp]
                    cards.append(build_scorers_card(comp_results, comp))
            actions = [{"type": "primary", "label": "Full Stats", "url": "https://www.google.com/search?q=" + query.replace(" ", "+")}]

    elif intent == "scores":
        results = search_matches(query, n_results=TOP_K)
        if results:
            context_parts = [r["text"] for r in results]
            cards = [match_to_card(r) for r in results]
            actions = [{"type": "primary", "label": "All Scores", "url": "https://www.google.com/search?q=football+scores+today"}]

    else:
        # General: search all collections
        match_results = search_matches(query, n_results=3)
        standing_results = search_standings(query, n_results=3)
        scorer_results = search_scorers(query, n_results=3)
        context_parts = (
            [r["text"] for r in match_results]
            + [r["text"] for r in standing_results]
            + [r["text"] for r in scorer_results]
        )
        cards = [match_to_card(r) for r in match_results[:2]]

    # Build LLM prompt with context
    if context_parts:
        context_block = "\n".join(context_parts)
        llm_prompt = f"Context:\n{context_block}\n\nUser question: {query}"
    else:
        llm_prompt = f"User question: {query}\n\n(No data found — provide a helpful general response)"

    system = SYSTEM_PROMPT
    if display_name:
        system += f"\nThe user's name is {display_name}. Address them by name occasionally."

    # SSE streaming or JSON response
    wants_stream = (
        STREAMING_ENABLED
        and "text/event-stream" in request.headers.get("accept", "")
    )

    if wants_stream:
        async def _event_stream() -> AsyncIterator[str]:
            prefix = f"Hey {display_name}! " if display_name else ""
            if prefix:
                yield f"data: {json.dumps({'type': 'delta', 'text': prefix})}\n\n"

            async for event in stream_llm(system, llm_prompt):
                yield event

            done_payload = json.dumps({
                "type": "done",
                "schema_version": SCHEMA_VERSION,
                "status": "completed",
                "cards": cards,
                "actions": actions,
            })
            yield f"data: {done_payload}\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    # Non-streaming JSON response
    llm_reply = await call_llm(system, llm_prompt)
    if display_name:
        llm_reply = f"Hey {display_name}! {llm_reply}"

    return JSONResponse({
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "content_parts": [{"type": "text", "text": llm_reply}],
        "cards": cards,
        "actions": actions,
    })


# ---------------------------------------------------------------------------
# Admin & utility endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "collections": {
            "matches": get_collection(COLLECTION_MATCHES).count(),
            "standings": get_collection(COLLECTION_STANDINGS).count(),
            "scorers": get_collection(COLLECTION_SCORERS).count(),
        },
        "vector_store": _vector_store_metadata(),
        "timestamp": time.time(),
    }


@app.get("/admin/status")
async def admin_status():
    return {
        "leagues": list(COMPETITIONS.keys()),
        "api_key_set": bool(FOOTBALL_DATA_API_KEY),
        "streaming_enabled": STREAMING_ENABLED,
        "refresh_interval": REFRESH_INTERVAL,
        "collections": {
            "matches": get_collection(COLLECTION_MATCHES).count(),
            "standings": get_collection(COLLECTION_STANDINGS).count(),
            "scorers": get_collection(COLLECTION_SCORERS).count(),
        },
    }


@app.post("/admin/refresh")
async def admin_refresh():
    if not FOOTBALL_DATA_API_KEY:
        raise HTTPException(status_code=400, detail="No FOOTBALL_DATA_API_KEY configured")
    client = FootballDataClient(FOOTBALL_DATA_API_KEY)
    totals = await run_full_ingest(client)
    return {"status": "refreshed", "totals": totals}


@app.post("/ingest")
async def ingest_all():
    if not FOOTBALL_DATA_API_KEY:
        raise HTTPException(status_code=400, detail="No FOOTBALL_DATA_API_KEY configured")
    client = FootballDataClient(FOOTBALL_DATA_API_KEY)
    totals = await run_full_ingest(client)
    return {"status": "ok", "totals": totals}


@app.post("/ingest/live")
async def ingest_live():
    if not FOOTBALL_DATA_API_KEY:
        raise HTTPException(status_code=400, detail="No FOOTBALL_DATA_API_KEY configured")
    client = FootballDataClient(FOOTBALL_DATA_API_KEY)
    count = await run_live_ingest(client)
    return {"status": "ok", "matches_updated": count}
