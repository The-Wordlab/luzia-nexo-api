"""Travel planning RAG partner webhook server.

This FastAPI application demonstrates a retrieval-augmented generation (RAG)
partner webhook for Nexo. It indexes travel destination profiles and travel
blog articles into pgvector, then serves a main webhook endpoint that:

1. Verifies the HMAC-SHA256 signature from Nexo.
2. Detects the user's intent (destinations, itineraries, budget, weather).
3. Searches the relevant pgvector collection(s).
4. Builds a RAG prompt and calls an LLM via litellm.
5. Returns a rich Nexo response envelope with text, destination cards, and actions.
6. Optionally streams the response as SSE (delta + done events).

Two pgvector-backed collections (managed by ingest.py):
  - "destinations"     Structured destination profiles with rich descriptions
  - "travel_articles"  RSS feed content from travel blogs

Endpoints:
  POST /             Main webhook endpoint (RAG + response)
  POST /ingest       Seed destinations + crawl travel RSS feeds
  GET  /health       Liveness probe / index stats

Environment variables:
  WEBHOOK_SECRET              HMAC secret for verifying Nexo requests
  LLM_MODEL                   litellm model string (default: vertex_ai/gemini-2.5-flash)
  EMBEDDING_MODEL             Embedding model (default: vertex_ai/text-embedding-004)
  TRAVEL_FEEDS                Comma-separated RSS feed URLs
  REFRESH_INTERVAL_MINUTES    Background refresh cadence (default: 60)
  STREAMING_ENABLED           Set to "true" to enable SSE streaming (default: false)
  TOP_K                       Number of results to retrieve (default: 4)

Webhook response envelope (canonical Nexo format):
    {
        "schema_version": "2026-03",
        "status": "completed",
        "content_parts": [{"type": "text", "text": "..."}],
        "cards":   [...],
        "actions": [...]
    }
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
from shared.streaming import stream_with_prefix

import ingest as _ingest_module
from ingest import (
    COLLECTION_ARTICLES,
    COLLECTION_DESTINATIONS,
    SEED_DESTINATIONS,
    crawl_feeds,
    embed_texts,
    get_collection,
    run_full_ingest,
    seed_destinations,
)

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
REFRESH_INTERVAL_MINUTES: int = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "60"))
STREAMING_ENABLED: bool = os.environ.get("STREAMING_ENABLED", "false").lower() == "true"
TOP_K: int = int(os.environ.get("TOP_K", "4"))
SESSION_DB_URL: str = os.environ.get("SESSION_DB_URL", os.environ.get("DATABASE_URL", ""))
SCHEMA_VERSION = "2026-03"
CAPABILITY_NAME = "travel.rag"
VECTOR_STORE_BACKEND: str = os.environ.get("VECTOR_STORE_BACKEND", "pgvector").strip().lower()
if VECTOR_STORE_BACKEND != "pgvector":
    raise RuntimeError(
        "travel-rag only supports VECTOR_STORE_BACKEND=pgvector. Remove any legacy vector-store override."
    )

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-travel-rag",
    "description": "Travel RAG webhook example for destinations, itineraries, budget, and weather guidance.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Answer travel planning questions with destination cards and actionable links.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["destination", "itinerary", "budget", "weather"],
                    "prompt_suggestions": [
                        "Best time to visit Paris?",
                        "Top activities in Bali",
                        "Build me a 5-day Lisbon itinerary",
                    ],
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

_DESTINATION_RE = re.compile(
    r"\b(destination|where|visit|go|travel to|country|city|place|recommend|suggestion|"
    r"best place|top place|must.?see|bucket list|explore|discover)\b",
    re.IGNORECASE,
)
_ITINERARY_RE = re.compile(
    r"\b(itinerary|plan|schedule|day.?trip|days|week|weekend|agenda|route|road.?trip|"
    r"what to do|things to do|activities|sightseeing|day 1|day 2|day 3)\b",
    re.IGNORECASE,
)
_BUDGET_RE = re.compile(
    r"\b(budget|cost|price|cheap|expensive|affordable|money|spend|how much|currency|"
    r"exchange|backpacker|luxury|economy|hostel|hotel)\b",
    re.IGNORECASE,
)
_WEATHER_RE = re.compile(
    r"\b(weather|climate|temperature|rain|rainy|sunny|season|summer|winter|monsoon|"
    r"best time|when to go|dry season|wet season|forecast)\b",
    re.IGNORECASE,
)


def detect_intent(message: str) -> str:
    """Return 'itinerary', 'budget', 'weather', or 'destination' based on keyword frequency."""
    itinerary_hits = len(_ITINERARY_RE.findall(message))
    budget_hits = len(_BUDGET_RE.findall(message))
    weather_hits = len(_WEATHER_RE.findall(message))
    destination_hits = len(_DESTINATION_RE.findall(message))

    scores = {
        "itinerary": itinerary_hits,
        "budget": budget_hits,
        "weather": weather_hits,
        "destination": destination_hits,
    }
    best = max(scores, key=lambda k: scores[k])
    # If all zero or tie with destination, default to destination
    if scores[best] == 0:
        return "destination"
    return best


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    suggestions = {
        "destination": [
            "Where should I go in Europe for 4 days?",
            "Recommend a warm destination in October",
            "What are the best places for first-time Japan travel?",
        ],
        "itinerary": [
            "Plan a 3-day itinerary for Barcelona",
            "Build a 5-day Tokyo plan with food and culture",
            "What should I do in Paris over a weekend?",
        ],
        "budget": [
            "What budget do I need for 1 week in Bali?",
            "How can I do Lisbon on a budget?",
            "Compare daily costs for Tokyo vs Barcelona",
        ],
        "weather": [
            "Best time to visit Paris?",
            "What is the weather like in Bali in July?",
            "When should I visit Japan for mild weather?",
        ],
    }
    return suggestions.get(intent, suggestions["destination"])


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
    payload_metadata: dict[str, Any] = {"prompt_suggestions": prompt_suggestions_for_intent(intent)}
    if metadata:
        payload_metadata.update(metadata)
    envelope = _shared_build_envelope(
        text=text,
        cards=cards,
        actions=actions,
        artifacts=artifacts,
        task_id=f"task_travel_{intent}",
        status=task_status,
        capability=CAPABILITY_NAME,
    )
    # Preserve top-level status for backward compatibility
    envelope["status"] = "error" if task_status in {"failed", "canceled"} else "completed"
    # Always include list fields even when empty for contract compliance
    envelope.setdefault("cards", [])
    envelope.setdefault("actions", [])
    envelope.setdefault("artifacts", [])
    envelope["metadata"] = payload_metadata
    return envelope


# ---------------------------------------------------------------------------
# Vector retrieval
# ---------------------------------------------------------------------------


def search_destinations(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    """Search the destinations collection. Returns destination dicts."""
    collection = get_collection(COLLECTION_DESTINATIONS)
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
                "city": meta.get("city", ""),
                "country": meta.get("country", ""),
                "region": meta.get("region", ""),
                "best_time": meta.get("best_time", ""),
                "budget_range": meta.get("budget_range", ""),
                "language": meta.get("language", ""),
                "currency": meta.get("currency", ""),
                "highlights": meta.get("highlights", ""),
                "tags": meta.get("tags", ""),
                "distance": results["distances"][0][i],
            }
        )
    return hits


def search_articles(query: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
    """Search the travel_articles collection. Returns article dicts."""
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
            max_tokens=500,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I'm having trouble generating a response right now. Please try again in a moment."


async def stream_llm_chunks(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream LLM response as plain text chunks.

    Yields plain text strings (not SSE-formatted). Callers pass this to
    ``stream_with_prefix`` from shared.streaming which handles SSE formatting.
    """
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=500,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
    except Exception as exc:
        logger.warning("LLM streaming failed: %s", exc)
        yield "I'm having trouble generating a response right now."


# Keep stream_llm as an alias so tests that monkeypatch it still work
stream_llm = stream_llm_chunks


# ---------------------------------------------------------------------------
# Card and action builders
# ---------------------------------------------------------------------------


def destination_to_card(dest: dict[str, Any]) -> dict[str, Any]:
    """Convert a destination search result to the Nexo card envelope format."""
    city = dest.get("city", "")
    country = dest.get("country", "")
    region = dest.get("region", "")
    highlights = dest.get("highlights", "")

    # Build a short description from the first sentence of the text
    raw_text = dest.get("text", "")
    description_start = raw_text.find("Description: ")
    if description_start != -1:
        description_text = raw_text[description_start + 13:]
        end = description_text.find("\n")
        description_text = description_text[:end] if end != -1 else description_text
        if len(description_text) > 200:
            description_text = description_text[:197] + "..."
    else:
        description_text = highlights[:200] if highlights else f"{city}, {country}"

    fields: list[dict[str, str]] = [
        {"label": "Best time", "value": dest.get("best_time", "")},
        {"label": "Budget", "value": dest.get("budget_range", "")},
        {"label": "Language", "value": dest.get("language", "")},
        {"label": "Currency", "value": dest.get("currency", "")},
    ]

    tags_raw = dest.get("tags", "")
    badges = [t.strip() for t in tags_raw.split(",") if t.strip()][:3]
    if not badges:
        badges = [region]

    return {
        "type": "destination",
        "title": f"{city}, {country}",
        "subtitle": region,
        "description": description_text,
        "badges": badges,
        "fields": fields,
        "metadata": {"capability_state": "live"},
    }


def build_itinerary_card(dest: dict[str, Any], days: int = 3) -> dict[str, Any]:
    """Build a suggested itinerary card for a destination."""
    city = dest.get("city", "")
    country = dest.get("country", "")
    highlights_raw = dest.get("highlights", "")
    highlights = [h.strip() for h in highlights_raw.split(",") if h.strip()]

    # Distribute highlights across days
    per_day = max(1, len(highlights) // days)
    day_plans: list[dict[str, str]] = []
    for day_num in range(1, days + 1):
        start = (day_num - 1) * per_day
        end = start + per_day if day_num < days else len(highlights)
        activities = ", ".join(highlights[start:end]) if highlights[start:end] else "Explore the city"
        day_plans.append({"label": f"Day {day_num}", "value": activities})

    return {
        "type": "itinerary",
        "title": f"{days}-Day {city} Itinerary",
        "subtitle": f"{city}, {country}",
        "description": f"A suggested {days}-day plan to make the most of your visit to {city}.",
        "badges": [f"{days} days", "Suggested"],
        "fields": day_plans,
        "metadata": {"capability_state": "live"},
    }


def build_destination_actions(destinations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build 'View on map' and 'Search flights' actions for top destinations."""
    actions: list[dict[str, Any]] = []
    for i, dest in enumerate(destinations[:2]):
        city = dest.get("city", "")
        country = dest.get("country", "")
        city_encoded = city.replace(" ", "+")
        country_encoded = country.replace(" ", "+")

        actions.append(
            {
                "id": f"view_map_{i + 1}",
                "label": f"View {city} on map",
                "url": f"https://www.google.com/maps/search/{city_encoded}+{country_encoded}",
                "style": "secondary",
            }
        )
        actions.append(
            {
                "id": f"search_flights_{i + 1}",
                "label": f"Search flights to {city}",
                "url": f"https://www.google.com/travel/flights?q=flights+to+{city_encoded}",
                "style": "secondary",
            }
        )
    return actions[:4]  # Cap at 4 actions


def build_article_actions(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build 'Read article' actions for travel content results."""
    actions = []
    for i, article in enumerate(articles[:3]):
        if article.get("link"):
            title = article.get("title", "Full article")
            actions.append(
                {
                    "id": f"read_article_{i + 1}",
                    "label": f"Read: {title[:50]}",
                    "url": article["link"],
                    "style": "secondary",
                }
            )
    return actions


# ---------------------------------------------------------------------------
# System prompt builders
# ---------------------------------------------------------------------------


def _destination_prompt(destinations: list[dict[str, Any]], articles: list[dict[str, Any]]) -> str:
    dest_context = "\n\n".join(d["text"][:600] for d in destinations) if destinations else ""
    article_context = "\n\n".join(a["text"][:300] for a in articles) if articles else ""
    context = dest_context
    if article_context:
        context += f"\n\nRelated travel articles:\n{article_context}"
    if not context:
        context = "No destination data available."
    return (
        "You are a knowledgeable travel advisor. Answer the user's question about travel "
        "destinations based on the provided destination profiles and articles. Be informative, "
        "inspiring, and practical. Highlight the best reasons to visit and key practical details.\n\n"
        f"Context:\n{context}"
    )


def _itinerary_prompt(destinations: list[dict[str, Any]]) -> str:
    context = "\n\n".join(d["text"][:600] for d in destinations) if destinations else "No destination data."
    return (
        "You are an expert travel planner. Create an engaging, practical itinerary suggestion "
        "for the user based on the destination profiles provided. Include specific places, "
        "experiences, and practical tips. Structure the response day-by-day if multiple days "
        "are mentioned.\n\n"
        f"Destination context:\n{context}"
    )


def _budget_prompt(destinations: list[dict[str, Any]]) -> str:
    context = "\n\n".join(d["text"][:500] for d in destinations) if destinations else "No destination data."
    return (
        "You are a budget travel expert. Answer the user's question about travel costs, "
        "budgeting, and money-saving tips based on the destination information provided. "
        "Include specific budget ranges, tips for saving money, and cost breakdowns where relevant.\n\n"
        f"Destination context:\n{context}"
    )


def _weather_prompt(destinations: list[dict[str, Any]]) -> str:
    context = "\n\n".join(d["text"][:500] for d in destinations) if destinations else "No destination data."
    return (
        "You are a travel climate expert. Answer the user's question about weather, climate, "
        "and the best times to visit based on the destination information provided. "
        "Give practical advice on what to pack and what to expect in different seasons.\n\n"
        f"Destination context:\n{context}"
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
        "Keep destination names, currencies, and itinerary fields readable."
    )


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _build_destination_response(
    query: str,
    destinations: list[dict[str, Any]],
    articles: list[dict[str, Any]],
    locale: str = "",
) -> dict[str, Any]:
    llm_reply = call_llm(_apply_language_instruction(_destination_prompt(destinations, articles), locale), query)
    cards = [destination_to_card(d) for d in destinations[:3]]
    actions = build_destination_actions(destinations)
    if not actions and articles:
        actions = build_article_actions(articles)
    return _build_envelope(
        text=llm_reply,
        intent="destination",
        cards=cards,
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "destinations",
                "data": destinations[:4],
            },
            {
                "type": "application/json",
                "name": "articles",
                "data": [
                    {"title": a.get("title"), "url": a.get("url"), "source": a.get("source")}
                    for a in articles[:5]
                ],
            },
        ],
    )


def _build_itinerary_response(query: str, destinations: list[dict[str, Any]], locale: str = "") -> dict[str, Any]:
    llm_reply = call_llm(_apply_language_instruction(_itinerary_prompt(destinations), locale), query)

    # Parse days from query (default 3)
    days_match = re.search(r"\b(\d+)\s*(?:-?\s*)?days?\b", query, re.IGNORECASE)
    num_days = min(int(days_match.group(1)), 7) if days_match else 3

    cards: list[dict[str, Any]] = []
    if destinations:
        cards.append(destination_to_card(destinations[0]))
        cards.append(build_itinerary_card(destinations[0], days=num_days))

    actions = build_destination_actions(destinations)

    return _build_envelope(
        text=llm_reply,
        intent="itinerary",
        cards=cards,
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "destinations",
                "data": destinations[:2],
            }
        ],
    )


def _build_budget_response(query: str, destinations: list[dict[str, Any]], locale: str = "") -> dict[str, Any]:
    llm_reply = call_llm(_apply_language_instruction(_budget_prompt(destinations), locale), query)
    cards = [destination_to_card(d) for d in destinations[:2]]
    actions = build_destination_actions(destinations)
    return _build_envelope(
        text=llm_reply,
        intent="budget",
        cards=cards,
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "destinations",
                "data": destinations[:2],
            }
        ],
    )


def _build_weather_response(query: str, destinations: list[dict[str, Any]], locale: str = "") -> dict[str, Any]:
    llm_reply = call_llm(_apply_language_instruction(_weather_prompt(destinations), locale), query)
    cards = [destination_to_card(d) for d in destinations[:2]]
    actions = build_destination_actions(destinations)
    return _build_envelope(
        text=llm_reply,
        intent="weather",
        cards=cards,
        actions=actions,
        artifacts=[
            {
                "type": "application/json",
                "name": "destinations",
                "data": destinations[:2],
            }
        ],
    )


def _no_results_response() -> dict[str, Any]:
    return _build_envelope(
        text=(
            "I don't have enough travel context to answer that right now. "
            "The index may still be loading - try again in a moment, or ask me about "
            "a specific destination like Paris, Tokyo, Barcelona, or Bali."
        ),
        intent="destination",
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
# Background refresh
# ---------------------------------------------------------------------------

_refresh_task: asyncio.Task | None = None


async def _background_refresh_loop() -> None:
    """Periodically re-crawl travel feeds."""
    while True:
        interval = REFRESH_INTERVAL_MINUTES * 60
        await asyncio.sleep(interval)
        logger.info("Background travel feed refresh triggered")
        try:
            await crawl_feeds()
        except Exception as exc:
            logger.warning("Background refresh failed: %s", exc)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


sessions: SessionStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _refresh_task, sessions

    if SESSION_DB_URL:
        try:
            sessions = SessionStore(SESSION_DB_URL)
            await sessions.init()
            logger.info("SessionStore initialised")
        except Exception:
            logger.warning("SessionStore init failed — session history disabled", exc_info=True)
            sessions = None

    logger.info("Travel RAG startup: seeding destination profiles...")
    seed_destinations()

    logger.info("Travel RAG startup: crawling travel RSS feeds...")
    try:
        await crawl_feeds()
    except Exception as exc:
        logger.warning("Initial feed crawl failed (demo works from seed data): %s", exc)

    _refresh_task = asyncio.create_task(_background_refresh_loop())
    logger.info(
        "Travel RAG ready. Collections: destinations=%d articles=%d",
        get_collection(COLLECTION_DESTINATIONS).count(),
        get_collection(COLLECTION_ARTICLES).count(),
    )

    yield

    if _refresh_task:
        _refresh_task.cancel()
    if sessions is not None:
        await sessions.close()


app = FastAPI(title="nexo-travel-rag-webhook", lifespan=lifespan)


@app.get("/.well-known/agent.json")
async def agent_card() -> JSONResponse:
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root() -> JSONResponse:
    """Service discovery endpoint for local/manual testing."""
    return JSONResponse(
        {
            "service": "webhook-travel-rag-python",
            "description": "Travel RAG webhook with destination and article retrieval plus structured cards.",
            "routes": [
                {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
                {"path": "/ingest", "method": "POST", "description": "Run full destination + RSS ingest"},
                {"path": "/health", "method": "GET", "description": "Collection counts and model config"},
            ],
            "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
            "schema_version": SCHEMA_VERSION,
        }
    )


# ---------------------------------------------------------------------------
# Main webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/", response_model=None)
async def receive_webhook(request: Request) -> JSONResponse | StreamingResponse:
    """Main Nexo webhook endpoint.

    Accepts the standard Nexo payload envelope, performs RAG over travel
    destination profiles and articles, and returns the Nexo response envelope
    with text, destination cards, and actions.

    When ``Accept: text/event-stream`` is present and ``STREAMING_ENABLED=true``,
    the response is streamed as SSE events.

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
    _require_signature(request, raw_body)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    message: dict[str, Any] = data.get("message") or {}
    profile: dict[str, Any] = data.get("profile") or {}
    thread: dict[str, Any] = data.get("thread") or {}
    thread_id: str = thread.get("id", "")
    query: str = message.get("content", "").strip()

    if not query:
        return JSONResponse(
            _build_envelope(
                text=(
                    "Ask me about travel! I can help you discover destinations, "
                    "plan itineraries, compare budgets, and find the best time to visit "
                    "cities around the world."
                ),
                intent="destination",
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

    # ---------------------------------------------------------------------------
    # Retrieve relevant context
    # ---------------------------------------------------------------------------

    destinations = search_destinations(query, n_results=TOP_K)
    articles: list[dict[str, Any]] = []

    if intent in ("destination", "weather", "budget") or not destinations:
        articles = search_articles(query, n_results=3)

    # Graceful no-results
    if not destinations and not articles:
        response_body = _no_results_response()
        if display_name:
            response_body = _personalise(response_body, display_name)
        return JSONResponse(response_body)

    # ---------------------------------------------------------------------------
    # Session history for follow-up context
    # ---------------------------------------------------------------------------

    history: list[dict[str, str]] = []
    if sessions is not None and thread_id:
        try:
            history = await sessions.get_history(thread_id, max_turns=10)
        except Exception:
            logger.warning("Failed to load session history", exc_info=True)

    # ---------------------------------------------------------------------------
    # SSE streaming path
    # ---------------------------------------------------------------------------

    if wants_stream:
        # Build cards, actions, artifacts for the intent
        if intent == "itinerary":
            system_prompt = _apply_language_instruction(_itinerary_prompt(destinations), locale)
            days_match = re.search(r"\b(\d+)\s*(?:-?\s*)?days?\b", query, re.IGNORECASE)
            num_days = min(int(days_match.group(1)), 7) if days_match else 3
            stream_cards: list[dict[str, Any]] = []
            if destinations:
                stream_cards.append(destination_to_card(destinations[0]))
                stream_cards.append(build_itinerary_card(destinations[0], days=num_days))
            stream_actions = build_destination_actions(destinations)
        elif intent == "budget":
            system_prompt = _apply_language_instruction(_budget_prompt(destinations), locale)
            stream_cards = [destination_to_card(d) for d in destinations[:2]]
            stream_actions = build_destination_actions(destinations)
        elif intent == "weather":
            system_prompt = _apply_language_instruction(_weather_prompt(destinations), locale)
            stream_cards = [destination_to_card(d) for d in destinations[:2]]
            stream_actions = build_destination_actions(destinations)
        else:
            system_prompt = _apply_language_instruction(_destination_prompt(destinations, articles), locale)
            stream_cards = [destination_to_card(d) for d in destinations[:3]]
            stream_actions = build_destination_actions(destinations)
            if not stream_actions and articles:
                stream_actions = build_article_actions(articles)

        stream_artifacts: list[dict[str, Any]] = []
        if destinations:
            stream_artifacts.append(
                {
                    "type": "application/json",
                    "name": "destinations",
                    "data": destinations[:4],
                }
            )
        if articles:
            stream_artifacts.append(
                {
                    "type": "application/json",
                    "name": "articles",
                    "data": [
                        {"title": a.get("title"), "url": a.get("url"), "source": a.get("source")}
                        for a in articles[:5]
                    ],
                }
            )

        envelope = _build_envelope(
            text="",
            intent=intent,
            cards=stream_cards,
            actions=stream_actions,
            artifacts=stream_artifacts,
        )

        prefix = _localized_prefix(locale, display_name)
        return StreamingResponse(
            stream_with_prefix(prefix, stream_llm_chunks(system_prompt, query), envelope),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---------------------------------------------------------------------------
    # JSON (non-streaming) path
    # ---------------------------------------------------------------------------

    if intent == "itinerary":
        response_body = _build_itinerary_response(query, destinations, locale=locale)
    elif intent == "budget":
        response_body = _build_budget_response(query, destinations, locale=locale)
    elif intent == "weather":
        response_body = _build_weather_response(query, destinations, locale=locale)
    else:
        response_body = _build_destination_response(query, destinations, articles, locale=locale)

    if display_name:
        response_body = _personalise(response_body, display_name)
        localized = _localized_prefix(locale, display_name)
        text = response_body["content_parts"][0]["text"]
        if localized and text.startswith(f"Hey {display_name}! "):
            response_body["content_parts"][0]["text"] = localized + text[len(f"Hey {display_name}! "):]

    # Persist conversation turns
    if sessions is not None and thread_id:
        try:
            reply_text = " ".join(
                p.get("text", "")
                for p in response_body.get("content_parts", [])
                if isinstance(p, dict) and p.get("type") == "text"
            )
            await sessions.add_turn(thread_id, "user", query)
            await sessions.add_turn(thread_id, "assistant", reply_text)
        except Exception:
            logger.warning("Failed to save session turn", exc_info=True)

    return JSONResponse(response_body)


# ---------------------------------------------------------------------------
# POST /ingest — seed + crawl on demand
# ---------------------------------------------------------------------------


@app.post("/ingest")
async def ingest_all() -> JSONResponse:
    """Trigger a full ingest: seed destination profiles + crawl RSS feeds.

    Runs synchronously and returns a summary. Use for initial population or
    on-demand refresh.
    """
    summary = await run_full_ingest()
    return JSONResponse(
        {
            "status": "ok",
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


# ---------------------------------------------------------------------------
# GET /health — liveness probe
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    """Return current index stats for liveness/readiness checks."""
    dest_count = get_collection(COLLECTION_DESTINATIONS).count()
    article_count = get_collection(COLLECTION_ARTICLES).count()
    return JSONResponse(
        {
            "status": "ok",
            "collections": {
                "destinations": dest_count,
                "travel_articles": article_count,
            },
            "llm_model": LLM_MODEL,
            "embedding_model": _ingest_module.EMBEDDING_MODEL,
            "streaming_enabled": STREAMING_ENABLED,
            "feeds": _ingest_module.TRAVEL_FEEDS,
            "vector_store": _vector_store_metadata(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )
