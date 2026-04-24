"""Sports-feed RAG partner webhook server.

This FastAPI application demonstrates a retrieval-augmented generation (RAG)
partner webhook for Nexo. It indexes sports RSS feeds and structured match
data into pgvector, then serves a main webhook endpoint that:

1. Verifies the HMAC-SHA256 signature from Nexo.
2. Detects the user's intent (scores/results, news, standings).
3. Searches the relevant pgvector collection(s).
4. Builds a RAG prompt and calls an LLM via litellm.
5. Returns a rich Nexo response envelope with text, cards, and actions.
6. Optionally streams the response as SSE (delta + done events).

Three pgvector-backed collections (managed by ingest.py):
  - "articles"       RSS feed content (news, previews, analysis)
  - "match_results"  Structured match results as text embeddings
  - "standings"      League table snapshots as text embeddings

Endpoints:
  GET  /health       Liveness probe (returns collection counts)
  POST /             Main webhook endpoint (RAG + response)
  POST /ingest       Crawl feeds + fetch live match results + standings
  POST /ingest/live  Lightweight: fetch only live match results + standings
  GET  /admin/status Index stats per collection + config
  POST /admin/refresh Re-crawl all sources (same as POST /ingest)

Environment variables:
  WEBHOOK_SECRET              HMAC secret for verifying Nexo requests
  LLM_MODEL                   litellm model string (default: vertex_ai/gemini-2.5-flash)
  EMBEDDING_MODEL             Embedding model (default: vertex_ai/text-embedding-004)
  SPORT_FEEDS                 Comma-separated RSS feed URLs
  FOOTBALL_DATA_API_KEY       football-data.org API key (optional)
  FOOTBALL_DATA_COMPETITION   Comma-separated competition IDs (default: PL)
  REFRESH_INTERVAL_MINUTES    Background refresh cadence (default: 15)
  STREAMING_ENABLED           Set to "true" to enable SSE streaming (default: false)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

# Add shared utilities to path (works both locally and in Docker container)
_here = Path(__file__).resolve().parent
for _ancestor in [_here.parent.parent, _here]:  # local: ../../shared, container: ./shared
    if (_ancestor / "shared").is_dir():
        sys.path.insert(0, str(_ancestor))
        break

import litellm
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from shared.envelope import build_envelope as _shared_build_envelope
from shared.sessions import SessionStore
from shared.streaming import stream_response as _stream_response  # noqa: F401 (available for callers)

import ingest as _ingest
from ingest import (
    COLLECTION_ARTICLES,
    COLLECTION_MATCHES,
    COLLECTION_STANDINGS,
    SEED_MATCHES,
    SEED_STANDINGS,
    embed_texts,
    fetch_live_matches,
    get_collection,
    run_full_ingest,
    run_live_ingest,
    seed_matches,
    seed_standings,
)
from event_detector import DetectedEvent, EventDetector
from event_store import EventStore
from match_state import MatchStateTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

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

WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
REFRESH_INTERVAL_MINUTES: int = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "15"))
STREAMING_ENABLED: bool = os.environ.get("STREAMING_ENABLED", "false").lower() == "true"
LIVE_POLL_INTERVAL_SECONDS: int = int(os.environ.get("LIVE_POLL_INTERVAL_SECONDS", "60"))
SESSION_DB_URL: str = os.environ.get("SESSION_DB_URL", os.environ.get("DATABASE_URL", ""))
TOP_K = 3
SCHEMA_VERSION = "2026-03"
CAPABILITY_NAME = "sports.rag"
VECTOR_STORE_BACKEND: str = os.environ.get("VECTOR_STORE_BACKEND", "pgvector").strip().lower()
if VECTOR_STORE_BACKEND != "pgvector":
    raise RuntimeError(
        "sports-rag only supports VECTOR_STORE_BACKEND=pgvector. Remove any legacy vector-store override."
    )

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-sports-rag",
    "description": "Broad sports flagship webhook example for scores, standings, fixtures, and sports news.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Answer broad sports questions with cards, source-backed context, and live-event awareness.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["scores", "standings", "news"],
                    "prompt_suggestions": [
                        "What are tonight's key fixtures across sports?",
                        "Who scored in today's matches?",
                        "Give me the latest Champions League update",
                    ],
                    "showcase_family": "sports",
                    "showcase_role": "primary",
                },
            }
        ]
    },
}


def _vector_store_metadata() -> dict[str, Any]:
    """Return runtime vector-store metadata for health/debug endpoints."""
    is_cloud_run = bool(os.environ.get("K_SERVICE"))
    return {
        "backend": "pgvector",
        "durable": True,
        "is_cloud_run": is_cloud_run,
    }

# ---------------------------------------------------------------------------
# Event detection — module-level singletons
# ---------------------------------------------------------------------------

_match_state_tracker: MatchStateTracker = MatchStateTracker()
_event_detector: EventDetector = EventDetector(
    llm_model=LLM_MODEL,
    significance_threshold=0.5,
)
_event_store: EventStore = EventStore()
_live_monitor_task: asyncio.Task | None = None

# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------


def _verify_signature(secret: str, raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Return True when the signature is valid."""
    if not secret or not timestamp or not signature:
        return False
    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _require_signature(request: Request, raw_body: bytes) -> None:
    """Raise HTTP 401 if WEBHOOK_SECRET is set and signature is invalid."""
    if not WEBHOOK_SECRET:
        return
    timestamp = request.headers.get("x-timestamp", "")
    signature = request.headers.get("x-signature", "")
    if not _verify_signature(WEBHOOK_SECRET, raw_body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

_SCORES_RE = re.compile(
    r"\b(score|result|results|win|won|lose|lost|draw|drew|goal|goals|beat|beaten|fixture|match|game|played|full.?time)\b",
    re.IGNORECASE,
)
_STANDINGS_RE = re.compile(
    r"\b(table|standing|standings|league table|position|rank|ranking|top|points|pts|first|second|third)\b",
    re.IGNORECASE,
)
_NEWS_RE = re.compile(
    r"\b(news|latest|update|report|preview|analysis|injury|injuries|transfer|signing|manager|squad|rumour|rumor)\b",
    re.IGNORECASE,
)


def detect_intent(message: str) -> str:
    """Return 'scores', 'standings', or 'news' based on keyword frequency."""
    scores_hits = len(_SCORES_RE.findall(message))
    standings_hits = len(_STANDINGS_RE.findall(message))
    news_hits = len(_NEWS_RE.findall(message))

    if standings_hits > scores_hits and standings_hits >= news_hits:
        return "standings"
    if scores_hits >= news_hits:
        return "scores"
    return "news"


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    suggestions = {
        "scores": [
            "Who scored in today's matches?",
            "Show me the latest Premier League results",
            "Did Arsenal win their last game?",
        ],
        "standings": [
            "Premier League standings",
            "Who is top of La Liga right now?",
            "Show the top 5 teams in Serie A",
        ],
        "news": [
            "Latest football transfer news",
            "Any injury updates this week?",
            "Summarize the top football headlines today",
        ],
    }
    return suggestions.get(intent, suggestions["scores"])


def _build_envelope(
    *,
    text: str,
    intent: str,
    cards: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    task_status: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload_metadata = {"prompt_suggestions": prompt_suggestions_for_intent(intent)}
    if metadata:
        payload_metadata.update(metadata)
    envelope = _shared_build_envelope(
        text=text,
        cards=cards,
        actions=actions,
        artifacts=artifacts,
        task_id=f"task_sports_{intent}",
        status=task_status,
        capability=CAPABILITY_NAME,
    )
    # Ensure cards/actions/artifacts always present for backward compatibility
    envelope.setdefault("cards", [])
    envelope.setdefault("actions", [])
    envelope.setdefault("artifacts", [])
    # Add top-level status (for backward compatibility) and metadata
    envelope["status"] = "error" if task_status in {"failed", "canceled"} else "completed"
    envelope["metadata"] = payload_metadata
    return envelope


# ---------------------------------------------------------------------------
# Vector retrieval
# ---------------------------------------------------------------------------


def search_matches(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    """Search the match_results collection. Returns a list of match dicts."""
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
        matches.append(
            {
                "id": results["ids"][0][i],
                "text": doc,
                "home_team": meta.get("home_team", ""),
                "away_team": meta.get("away_team", ""),
                "home_score": int(meta.get("home_score", 0)),
                "away_score": int(meta.get("away_score", 0)),
                "competition": meta.get("competition", ""),
                "date": meta.get("date", ""),
                "venue": meta.get("venue", ""),
                "goals": meta.get("goals", ""),
                "matchday": meta.get("matchday", ""),
                "status": meta.get("status", "FINISHED"),
                "distance": results["distances"][0][i],
            }
        )
    return matches


def search_articles(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    """Search the articles collection. Returns a list of article dicts."""
    collection = get_collection(COLLECTION_ARTICLES)
    count = collection.count()
    if count == 0:
        return []

    embeddings = embed_texts([query])
    results = collection.query(
        query_embeddings=embeddings,
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )

    articles: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        articles.append(
            {
                "text": doc,
                "title": meta.get("title", ""),
                "link": meta.get("link", ""),
                "feed": meta.get("feed", ""),
                "published": meta.get("published", ""),
                "excerpt": meta.get("excerpt", doc[:150]),
                "distance": results["distances"][0][i],
            }
        )
    return articles


def search_standings(query: str, n_results: int = 1) -> list[dict[str, Any]]:
    """Search the standings collection. Returns a list of standings dicts."""
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

    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        hits.append(
            {
                "text": doc,
                "competition": meta.get("competition", ""),
                "date": meta.get("date", ""),
                "top_team": meta.get("top_team", ""),
            }
        )
    return hits


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def call_llm(system_prompt: str, user_message: str) -> str:
    """Call the configured LLM and return the reply text."""
    try:
        response = litellm.completion(
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
        return "I'm having trouble generating a response right now. Please try again in a moment."


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream LLM response tokens as SSE events.

    Yields:
        SSE-formatted lines: ``data: {...}\\n\\n``
    The final event is ``data: {"type": "done"}\\n\\n``.
    """
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
                payload = json.dumps({"type": "content_delta", "text": delta})
                yield f"event: content_delta\ndata: {payload}\n\n"
    except Exception as exc:
        logger.warning("LLM streaming failed: %s", exc)
        error_text = "I'm having trouble generating a response right now."
        payload = json.dumps({"type": "content_delta", "text": error_text})
        yield f"event: content_delta\ndata: {payload}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ---------------------------------------------------------------------------
# Card and action builders
# ---------------------------------------------------------------------------


def match_to_card(match: dict[str, Any]) -> dict[str, Any]:
    """Convert a match dict to the Nexo card envelope format."""
    score_line = f"{match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}"
    subtitle = f"{match['competition']} - Matchday {match['matchday']}"
    fields: list[dict[str, str]] = [
        {"label": "Date", "value": str(match["date"])},
        {"label": "Venue", "value": match.get("venue") or "N/A"},
    ]
    if match.get("goals"):
        fields.append({"label": "Goals", "value": match["goals"][:100]})

    return {
        "type": "match_result",
        "title": score_line,
        "subtitle": subtitle,
        "description": f"Goals: {match['goals']}" if match.get("goals") else subtitle,
        "badges": [match["competition"], "Full Time"],
        "fields": fields,
        "metadata": {"capability_state": "live"},
    }


def build_standings_card(standings: list[dict[str, Any]], competition: str, label: str) -> dict[str, Any]:
    """Build a standings_table card for the top entries."""
    top5 = standings[:5]
    return {
        "type": "standings_table",
        "title": f"{competition} Table",
        "subtitle": label,
        "badges": [competition, "2025/26"],
        "fields": [
            {"label": f"{s['position']}. {s['team']}", "value": f"{s['points']} pts"}
            for s in top5
        ],
        "metadata": {"capability_state": "live"},
    }


def build_article_card(article: dict[str, Any]) -> dict[str, Any] | None:
    """Build a news_article card from an article dict."""
    if not article.get("title"):
        return None
    excerpt = article.get("excerpt") or article.get("text", "")
    if len(excerpt) > 160:
        excerpt = excerpt[:157] + "..."
    return {
        "type": "news_article",
        "title": article["title"],
        "subtitle": article.get("published", ""),
        "description": excerpt,
        "badges": ["Football News"],
        "fields": [{"label": "Source", "value": (article.get("link") or "")[:80]}],
        "metadata": {"capability_state": "live"},
    }


def build_match_actions(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build 'View match details' actions for each match (up to 3)."""
    actions = []
    for i, match in enumerate(matches[:3]):
        # Generate a search URL as a placeholder; partners should replace with real deep links
        teams = f"{match['home_team']} vs {match['away_team']}".replace(" ", "+")
        competition = match.get("competition", "").replace(" ", "+")
        actions.append(
            {
                "id": f"view_match_{i + 1}",
                "label": f"View match details: {match['home_team']} vs {match['away_team']}",
                "url": f"https://www.google.com/search?q={teams}+{competition}+result",
                "style": "secondary",
            }
        )
    return actions


def build_standings_actions(competition: str) -> list[dict[str, Any]]:
    """Build a 'See full standings' action."""
    comp_slug = competition.lower().replace(" ", "-")
    return [
        {
            "id": "view_standings",
            "label": f"See full {competition} standings",
            "url": f"https://www.bbc.co.uk/sport/football/{comp_slug}/table",
            "style": "secondary",
        }
    ]


def build_article_actions(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build 'Read article' actions for news results."""
    actions = []
    for i, article in enumerate(articles[:3]):
        if article.get("link"):
            actions.append(
                {
                    "id": f"read_article_{i + 1}",
                    "label": f"Read: {article.get('title', 'Full article')[:50]}",
                    "url": article["link"],
                    "style": "secondary",
                }
            )
    return actions


# ---------------------------------------------------------------------------
# System prompt builders
# ---------------------------------------------------------------------------


def _scores_prompt(matches: list[dict[str, Any]]) -> str:
    context = "\n".join(m["text"] for m in matches) if matches else "No recent match data available."
    return (
        "You are a football analyst assistant. Answer the user's question about match results "
        "using only the provided context. Be concise and factual. Focus on the specific teams "
        "or competition the user asked about.\n\n"
        f"Match context:\n{context}"
    )


def _standings_prompt(standings_docs: list[dict[str, Any]], extra_context: str = "") -> str:
    standings_text = "\n\n".join(d["text"] for d in standings_docs) if standings_docs else ""
    if not standings_text:
        # Fall back to seed data
        lines = [
            f"{s['position']}. {s['team']}: P{s['played']} W{s['won']} D{s['drawn']} "
            f"L{s['lost']} GD{s['gd']:+d} Pts{s['points']}"
            for s in SEED_STANDINGS
        ]
        standings_text = "Premier League Table (Matchday 28, March 2026):\n" + "\n".join(lines)

    context = standings_text
    if extra_context:
        context += f"\n\nRecent news:\n{extra_context}"

    return (
        "You are a football analyst. Answer the user's question about league standings "
        "based on the data provided. Be concise and accurate.\n\n"
        f"Context:\n{context}"
    )


def _news_prompt(articles: list[dict[str, Any]]) -> str:
    context = "\n\n".join(a["text"][:300] for a in articles) if articles else "No recent news available."
    return (
        "You are a football news journalist. Answer the user's question using the article "
        "excerpts provided as context. Be informative and engaging.\n\n"
        f"Context:\n{context}"
    )


def _get_locale(profile: dict[str, Any]) -> str:
    locale = profile.get("locale") or profile.get("language") or ""
    return str(locale).strip()


def _localized_prefix(locale: str, display_name: str) -> str:
    if not display_name:
        return ""
    lowered = locale.lower()
    if lowered.startswith("pt"):
        return f"Oi {display_name}! "
    if lowered.startswith("fr"):
        return f"Salut {display_name}! "
    if lowered.startswith("it"):
        return f"Ciao {display_name}! "
    if lowered.startswith("ja"):
        return f"{display_name}さん、こんにちは！ "
    if lowered.startswith("es"):
        return f"Hola {display_name}! "
    return f"Hey {display_name}! "


def _apply_language_instruction(system_prompt: str, locale: str) -> str:
    if not locale:
        return system_prompt
    return (
        system_prompt
        + f"\n\nRespond in the user's preferred language ({locale}) for all free-form text. "
        "Keep team names, competition names, and scores unchanged when useful."
    )


# ---------------------------------------------------------------------------
# Response builders (synchronous, for non-streaming path)
# ---------------------------------------------------------------------------


def build_scores_response(query: str, matches: list[dict[str, Any]], locale: str = "") -> dict[str, Any]:
    """Build a full Nexo response envelope for a scores/results query."""
    llm_reply = call_llm(_apply_language_instruction(_scores_prompt(matches), locale), query)
    cards = [match_to_card(m) for m in matches[:3]]
    actions = build_match_actions(matches)

    return _build_envelope(
        text=llm_reply,
        intent="scores",
        cards=cards,
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "matches",
                "data": matches[:3],
            }
        ],
    )


def build_standings_response(query: str, standings_docs: list[dict[str, Any]], locale: str = "") -> dict[str, Any]:
    """Build a full Nexo response envelope for a standings query."""
    llm_reply = call_llm(_apply_language_instruction(_standings_prompt(standings_docs), locale), query)

    # Determine competition from retrieved doc or default to Premier League
    competition = "Premier League"
    if standings_docs and standings_docs[0].get("competition"):
        competition = standings_docs[0]["competition"]

    # Use SEED_STANDINGS for card rendering (always available)
    standings_card = build_standings_card(
        SEED_STANDINGS, competition, label="Matchday 28 - March 2026"
    )
    actions = build_standings_actions(competition)

    return _build_envelope(
        text=llm_reply,
        intent="standings",
        cards=[standings_card],
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "standings",
                "data": SEED_STANDINGS[:10],
            }
        ],
    )


def build_news_response(query: str, articles: list[dict[str, Any]], locale: str = "") -> dict[str, Any]:
    """Build a full Nexo response envelope for a news query."""
    llm_reply = call_llm(_apply_language_instruction(_news_prompt(articles), locale), query)
    cards = [c for a in articles[:3] if (c := build_article_card(a)) is not None]
    actions = build_article_actions(articles)

    return _build_envelope(
        text=llm_reply,
        intent="news",
        cards=cards,
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "articles",
                "data": [
                    {
                        "title": a.get("title"),
                        "url": a.get("url"),
                        "source": a.get("source"),
                    }
                    for a in articles[:5]
                ],
            }
        ],
    )


def build_no_results_response() -> dict[str, Any]:
    """Return a graceful no-results envelope."""
    return _build_envelope(
        text=(
            "I don't have enough sports context to answer that question right now. "
            "The index may still be loading - try again in a moment, or ask me about "
            "recent Premier League scores, standings, or transfer news."
        ),
        intent="news",
    )


# ---------------------------------------------------------------------------
# Personalisation
# ---------------------------------------------------------------------------


def _personalise(response: dict[str, Any], display_name: str) -> dict[str, Any]:
    """Prepend 'Hey {name}!' to the first text content part."""
    parts = response.get("content_parts", [])
    if parts and parts[0].get("type") == "text":
        parts[0]["text"] = f"Hey {display_name}! {parts[0]['text']}"
    return response


# ---------------------------------------------------------------------------
# Event detection cycle
# ---------------------------------------------------------------------------


async def run_detection_cycle() -> list[DetectedEvent]:
    """Fetch live matches, run state tracker, store any detected events.

    Returns the list of DetectedEvent objects that passed the significance
    threshold and were stored. Returns an empty list on any fetch failure.
    """
    try:
        current_matches = await fetch_live_matches()
    except Exception as exc:
        logger.warning("Detection cycle: fetch_live_matches failed: %s", exc)
        return []

    match_events = _match_state_tracker.track(current_matches)
    detected: list[DetectedEvent] = []

    for match_event in match_events:
        event = _event_detector.evaluate_match_event(match_event)
        if event is None:
            continue
        try:
            _event_store.store(event)
        except Exception as exc:
            logger.warning("Detection cycle: store failed for %s: %s", event.event_type, exc)
            continue
        logger.info(
            "Event detected: %s (significance=%.2f) — %s",
            event.event_type,
            event.significance,
            event.summary[:80],
        )
        detected.append(event)

    return detected


# ---------------------------------------------------------------------------
# Background refresh
# ---------------------------------------------------------------------------

_refresh_task: asyncio.Task | None = None


async def _background_refresh_loop() -> None:
    """Periodically re-crawl feeds and refresh live match data, then run event detection."""
    while True:
        interval = REFRESH_INTERVAL_MINUTES * 60
        await asyncio.sleep(interval)
        logger.info("Background refresh triggered")
        try:
            await run_full_ingest()
        except Exception as exc:
            logger.warning("Background refresh failed: %s", exc)

        # After ingest, run event detection
        try:
            events = await run_detection_cycle()
            if events:
                logger.info("Background refresh: %d event(s) detected", len(events))
        except Exception as exc:
            logger.warning("Background refresh: event detection failed: %s", exc)


async def _live_monitor_loop() -> None:
    """Faster polling loop for live match event detection.

    Polls at LIVE_POLL_INTERVAL_SECONDS (default 60s) regardless of the
    slower RSS crawl cadence. Only runs detection — does not re-crawl feeds.
    """
    while True:
        await asyncio.sleep(LIVE_POLL_INTERVAL_SECONDS)
        logger.debug("Live monitor poll triggered")
        try:
            events = await run_detection_cycle()
            if events:
                logger.info("Live monitor: %d event(s) detected", len(events))
        except Exception as exc:
            logger.warning("Live monitor failed: %s", exc)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


sessions: SessionStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _refresh_task, _live_monitor_task, sessions

    if SESSION_DB_URL:
        sessions = SessionStore(SESSION_DB_URL)
        await sessions.init()

    logger.info("Sports RAG startup: seeding data...")
    seed_matches()
    seed_standings()

    logger.info("Sports RAG startup: crawling RSS feeds...")
    try:
        await _ingest.crawl_feeds()
    except Exception as exc:
        logger.warning("Initial feed crawl failed (demo will work from seed data): %s", exc)

    _refresh_task = asyncio.create_task(_background_refresh_loop())
    _live_monitor_task = asyncio.create_task(_live_monitor_loop())
    logger.info(
        "Sports RAG ready. Collections: articles=%d match_results=%d standings=%d",
        get_collection(COLLECTION_ARTICLES).count(),
        get_collection(COLLECTION_MATCHES).count(),
        get_collection(COLLECTION_STANDINGS).count(),
    )

    yield

    if _refresh_task:
        _refresh_task.cancel()
    if _live_monitor_task:
        _live_monitor_task.cancel()
    if sessions:
        await sessions.close()


app = FastAPI(title="nexo-sports-rag-webhook", lifespan=lifespan)


@app.get("/.well-known/agent.json")
async def agent_card() -> JSONResponse:
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root() -> JSONResponse:
    """Service discovery endpoint for local/manual testing."""
    return JSONResponse(
        {
            "service": "webhook-sports-rag-python",
            "description": "Broad sports flagship webhook with intent routing, streaming, and live event detection.",
            "routes": [
                {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
                {"path": "/health", "method": "GET", "description": "Collection counts and runtime state"},
                {"path": "/ingest", "method": "POST", "description": "Full ingest (articles, matches, standings)"},
                {"path": "/ingest/live", "method": "POST", "description": "Live-only ingest"},
                {"path": "/admin/status", "method": "GET", "description": "Admin status summary"},
                {"path": "/admin/events", "method": "GET", "description": "Recent detected events"},
                {"path": "/admin/detect", "method": "POST", "description": "Force one event detection cycle"},
            ],
            "showcase": {
                "family": "sports",
                "role": "primary",
            },
            "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
            "schema_version": SCHEMA_VERSION,
        }
    )


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe — returns index stats per collection."""
    return JSONResponse(
        {
            "status": "ok",
            "collections": {
                "articles": get_collection(COLLECTION_ARTICLES).count(),
                "match_results": get_collection(COLLECTION_MATCHES).count(),
                "standings": get_collection(COLLECTION_STANDINGS).count(),
            },
            "llm_model": LLM_MODEL,
            "streaming_enabled": STREAMING_ENABLED,
            "vector_store": _vector_store_metadata(),
        }
    )


# ---------------------------------------------------------------------------
# Main webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/", response_model=None)
async def receive_webhook(request: Request) -> JSONResponse | StreamingResponse:
    """Main Nexo webhook endpoint.

    Accepts the standard Nexo payload envelope, performs RAG over sports
    content, and returns the Nexo response envelope with text, cards, and
    actions.

    When ``Accept: text/event-stream`` is present in the request headers and
    ``STREAMING_ENABLED=true``, the response is streamed as SSE events.
    """
    raw_body = await request.body()
    _require_signature(request, raw_body)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    message: dict[str, Any] = data.get("message") or {}
    profile: dict[str, Any] = data.get("profile") or {}
    thread_id: str = data.get("thread_id") or data.get("session_id") or ""
    query: str = message.get("content", "").strip()

    # Load session state (conversation history + favourite teams)
    session: dict[str, Any] = await sessions.get(thread_id) if (sessions and thread_id) else {}
    favourite_teams: list[str] = session.get("favourite_teams", [])

    # Empty query - provide a helpful prompt
    if not query:
        return JSONResponse(
            _build_envelope(
                text=(
                    "Ask me about football! I can help with match results, "
                    "league standings, transfer news, and more."
                ),
                intent="scores",
            )
        )

    intent = detect_intent(query)
    logger.info("Query: %r | Intent: %s", query[:80], intent)

    display_name: str = profile.get("display_name") or profile.get("name") or ""
    locale = _get_locale(profile)
    wants_stream = (
        STREAMING_ENABLED
        and "text/event-stream" in request.headers.get("accept", "")
    )

    # Persist user turn and update favourite teams if mentioned
    if sessions and thread_id and query:
        await sessions.add_turn(thread_id, "user", query)
        # Extract any team mentions to track favourites across turns
        mentioned = [t for t in ["Arsenal", "Liverpool", "Chelsea", "Man City", "Tottenham", "Barcelona", "Real Madrid"] if t.lower() in query.lower()]
        if mentioned:
            updated_teams = list(dict.fromkeys(favourite_teams + mentioned))[:5]
            if updated_teams != favourite_teams:
                await sessions.update(thread_id, favourite_teams=updated_teams)

    # ---------------------------------------------------------------------------
    # Retrieve relevant context
    # ---------------------------------------------------------------------------

    if intent == "scores":
        matches = search_matches(query)
        articles: list[dict[str, Any]] = []
        standings_docs: list[dict[str, Any]] = []
    elif intent == "standings":
        standings_docs = search_standings(query)
        articles = search_articles(query, n_results=2)
        matches = []
    else:  # news
        articles = search_articles(query)
        matches = []
        standings_docs = []
        # Also try matches if no articles found
        if not articles:
            matches = search_matches(query)
            intent = "scores"

    # Graceful no-results
    if not matches and not articles and not standings_docs:
        response_body = build_no_results_response()
        if display_name:
            response_body = _personalise(response_body, display_name)
        return JSONResponse(response_body)

    # ---------------------------------------------------------------------------
    # SSE streaming path
    # ---------------------------------------------------------------------------

    if wants_stream:

        async def _event_stream() -> AsyncIterator[str]:
            # Determine prompt based on intent
            if intent == "scores":
                system_prompt = _apply_language_instruction(_scores_prompt(matches), locale)
                cards = [match_to_card(m) for m in matches[:3]]
                actions = build_match_actions(matches)
            elif intent == "standings":
                system_prompt = _apply_language_instruction(_standings_prompt(standings_docs), locale)
                competition = standings_docs[0].get("competition", "Premier League") if standings_docs else "Premier League"
                cards = [build_standings_card(SEED_STANDINGS, competition, "Matchday 28 - March 2026")]
                actions = build_standings_actions(competition)
            else:
                system_prompt = _apply_language_instruction(_news_prompt(articles), locale)
                cards = [c for a in articles[:3] if (c := build_article_card(a)) is not None]
                actions = build_article_actions(articles)
            artifacts: list[dict[str, Any]] = []
            if intent == "scores":
                artifacts = [{"type": "application/json", "name": "matches", "data": matches[:3]}]
            elif intent == "standings":
                artifacts = [{"type": "application/json", "name": "standings", "data": SEED_STANDINGS[:10]}]
            elif intent == "news":
                artifacts = [
                    {
                        "type": "application/json",
                        "name": "articles",
                        "data": [
                            {"title": a.get("title"), "url": a.get("url"), "source": a.get("source")}
                            for a in articles[:5]
                        ],
                    }
                ]

            envelope = _build_envelope(
                text="",
                intent=intent,
                cards=cards,
                actions=actions,
                artifacts=artifacts,
            )
            task = envelope["task"]
            yield (
                "event: task.started\ndata: "
                + json.dumps({"task": {"id": task["id"], "status": "in_progress"}})
                + "\n\n"
            )

            # Prefix with personalisation token so client can prepend if desired
            prefix = _localized_prefix(locale, display_name)
            if prefix:
                yield f"event: content_delta\ndata: {json.dumps({'type': 'content_delta', 'text': prefix})}\n\n"
                yield f"event: task.delta\ndata: {json.dumps({'text': prefix})}\n\n"

            async for event in stream_llm(system_prompt, query):
                if event.startswith("event: content_delta") or (
                    event.startswith("data:") and not event.startswith("event:")
                ):
                    try:
                        # Extract data portion for named events
                        data_line = event
                        if "\ndata:" in event:
                            data_line = event.split("\ndata:", 1)[1].strip()
                        elif event.startswith("data:"):
                            data_line = event[len("data:"):].strip()
                        payload = json.loads(data_line)
                    except (json.JSONDecodeError, ValueError):
                        yield event
                        continue
                    ptype = payload.get("type", "")
                    if ptype in ("content_delta", "delta"):
                        yield f"event: content_delta\ndata: {json.dumps({'type': 'content_delta', 'text': payload.get('text', '')})}\n\n"
                        yield f"event: task.delta\ndata: {json.dumps({'text': payload.get('text', '')})}\n\n"
                        continue
                    if payload.get("type") == "done":
                        continue
                yield event

            for artifact in artifacts:
                yield f"event: task.artifact\ndata: {json.dumps(artifact)}\n\n"

            done_envelope = _build_envelope(
                text=prefix.strip(),
                intent=intent,
                cards=cards,
                actions=actions,
                artifacts=artifacts,
            )
            done_payload = {"type": "done", **done_envelope}
            yield "event: done\ndata: " + json.dumps(done_payload) + "\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    # ---------------------------------------------------------------------------
    # JSON (non-streaming) path
    # ---------------------------------------------------------------------------

    if intent == "scores":
        response_body = build_scores_response(query, matches, locale=locale)
    elif intent == "standings":
        response_body = build_standings_response(query, standings_docs, locale=locale)
    else:
        response_body = build_news_response(query, articles, locale=locale)

    if display_name:
        response_body = _personalise(response_body, display_name)
        localized = _localized_prefix(locale, display_name)
        text = response_body["content_parts"][0]["text"]
        if localized and text.startswith(f"Hey {display_name}! "):
            response_body["content_parts"][0]["text"] = localized + text[len(f"Hey {display_name}! "):]

    # Record assistant turn in session history
    if sessions and thread_id:
        reply_text = ""
        parts = response_body.get("content_parts", [])
        if parts and parts[0].get("type") == "text":
            reply_text = parts[0]["text"]
        await sessions.add_turn(thread_id, "assistant", reply_text)

    return JSONResponse(response_body)


# ---------------------------------------------------------------------------
# Ingest endpoints
# ---------------------------------------------------------------------------


@app.post("/ingest")
async def ingest_all() -> JSONResponse:
    """Trigger a full ingest: RSS feeds + live match results + standings.

    The ingest runs synchronously and returns a summary of items indexed.
    Use this endpoint to populate the index before serving webhook requests,
    or to force a refresh on demand.
    """
    summary = await run_full_ingest()
    return JSONResponse(
        {
            "status": "ok",
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@app.post("/ingest/live")
async def ingest_live() -> JSONResponse:
    """Trigger a lightweight ingest: live match results + standings only.

    Faster than POST /ingest because it skips the RSS feed crawl.
    Ideal for high-frequency polling (e.g., every 5 minutes during live matches).
    """
    summary = await run_live_ingest()
    return JSONResponse(
        {
            "status": "ok",
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@app.get("/admin/status")
async def admin_status() -> JSONResponse:
    """Return index statistics and server configuration."""
    articles_count = get_collection(COLLECTION_ARTICLES).count()
    matches_count = get_collection(COLLECTION_MATCHES).count()
    standings_count = get_collection(COLLECTION_STANDINGS).count()

    return JSONResponse(
        {
            "status": "ok",
            "collections": {
                "articles": {"count": articles_count},
                "match_results": {"count": matches_count},
                "standings": {"count": standings_count},
            },
            "config": {
                "llm_model": LLM_MODEL,
                "embedding_model": _ingest.EMBEDDING_MODEL,
                "refresh_interval_minutes": REFRESH_INTERVAL_MINUTES,
                "feeds": _ingest.SPORT_FEEDS,
                "streaming_enabled": STREAMING_ENABLED,
                "football_data_api_configured": bool(_ingest.FOOTBALL_DATA_API_KEY),
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@app.post("/admin/refresh")
async def admin_refresh(background_tasks: BackgroundTasks) -> JSONResponse:
    """Queue a full background re-ingest (same as POST /ingest)."""
    background_tasks.add_task(run_full_ingest)
    return JSONResponse(
        {
            "status": "refresh_scheduled",
            "message": "Full ingest queued in background.",
        }
    )


@app.get("/admin/events")
async def admin_events(
    type: str | None = None,
    team: str | None = None,
    limit: int = 20,
) -> JSONResponse:
    """Return recent detected events from the event store.

    Query parameters:
      type   Filter by event_type (e.g. "goal", "score_change", "match_start")
      team   Filter to events involving this team name
      limit  Maximum number of results to return (default 20)
    """
    events = _event_store.query(
        event_type=type,
        team=team,
        limit=limit,
    )
    return JSONResponse(
        {
            "status": "ok",
            "events": events,
            "total": len(events),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@app.post("/admin/detect")
async def admin_detect() -> JSONResponse:
    """Manually trigger an event detection cycle (for testing/debugging).

    Runs the same logic as the live monitor background loop: fetches current
    match states, diffs against previous, stores any new events, and returns
    the list of detected events in this cycle.
    """
    detected = await run_detection_cycle()
    serialised = [
        {
            "event_type": e.event_type,
            "significance": e.significance,
            "summary": e.summary,
            "detail": e.detail,
            "teams": e.teams,
            "card": e.card,
            "timestamp": e.timestamp.isoformat(),
            "content_hash": e.content_hash,
        }
        for e in detected
    ]
    return JSONResponse(
        {
            "status": "ok",
            "events_detected": len(detected),
            "events": serialised,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )
