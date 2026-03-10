"""Travel planning RAG partner webhook server.

This FastAPI application demonstrates a retrieval-augmented generation (RAG)
partner webhook for Nexo. It indexes travel destination profiles and travel
blog articles into ChromaDB, then serves a main webhook endpoint that:

1. Verifies the HMAC-SHA256 signature from Nexo.
2. Detects the user's intent (destinations, itineraries, budget, weather).
3. Searches the relevant ChromaDB collection(s).
4. Builds a RAG prompt and calls an LLM via litellm.
5. Returns a rich Nexo response envelope with text, destination cards, and actions.
6. Optionally streams the response as SSE (delta + done events).

Two ChromaDB collections (managed by ingest.py):
  - "destinations"     Structured destination profiles with rich descriptions
  - "travel_articles"  RSS feed content from travel blogs

Endpoints:
  POST /             Main webhook endpoint (RAG + response)
  POST /ingest       Seed destinations + crawl travel RSS feeds
  GET  /health       Liveness probe / index stats

Environment variables:
  WEBHOOK_SECRET              HMAC secret for verifying Nexo requests
  LLM_MODEL                   litellm model string (default: ollama/llama3.2)
  EMBEDDING_MODEL             Embedding model (default: text-embedding-3-small)
  TRAVEL_FEEDS                Comma-separated RSS feed URLs
  REFRESH_INTERVAL_MINUTES    Background refresh cadence (default: 60)
  CHROMA_PERSIST_DIR          ChromaDB persistence path (default: ./chroma_data)
  STREAMING_ENABLED           Set to "true" to enable SSE streaming (default: false)
  TOP_K                       Number of results to retrieve (default: 4)

Webhook response envelope (canonical Nexo format):
    {
        "schema_version": "2026-03-01",
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
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

import litellm
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

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

WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "ollama/llama3.2")
REFRESH_INTERVAL_MINUTES: int = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "60"))
STREAMING_ENABLED: bool = os.environ.get("STREAMING_ENABLED", "false").lower() == "true"
TOP_K: int = int(os.environ.get("TOP_K", "4"))
VECTOR_STORE_BACKEND: str = os.environ.get("VECTOR_STORE_BACKEND", "chroma").strip().lower()
VECTOR_STORE_DURABLE_OVERRIDE: str = os.environ.get("VECTOR_STORE_DURABLE", "").strip().lower()


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


# ---------------------------------------------------------------------------
# ChromaDB retrieval
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
            max_tokens=500,
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

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


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


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _build_destination_response(
    query: str,
    destinations: list[dict[str, Any]],
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    llm_reply = call_llm(_destination_prompt(destinations, articles), query)
    cards = [destination_to_card(d) for d in destinations[:3]]
    actions = build_destination_actions(destinations)
    if not actions and articles:
        actions = build_article_actions(articles)
    return {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [{"type": "text", "text": llm_reply}],
        "cards": cards,
        "actions": actions,
    }


def _build_itinerary_response(query: str, destinations: list[dict[str, Any]]) -> dict[str, Any]:
    llm_reply = call_llm(_itinerary_prompt(destinations), query)

    # Parse days from query (default 3)
    days_match = re.search(r"\b(\d+)\s*(?:-?\s*)?days?\b", query, re.IGNORECASE)
    num_days = min(int(days_match.group(1)), 7) if days_match else 3

    cards: list[dict[str, Any]] = []
    if destinations:
        cards.append(destination_to_card(destinations[0]))
        cards.append(build_itinerary_card(destinations[0], days=num_days))

    actions = build_destination_actions(destinations)

    return {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [{"type": "text", "text": llm_reply}],
        "cards": cards,
        "actions": actions,
    }


def _build_budget_response(query: str, destinations: list[dict[str, Any]]) -> dict[str, Any]:
    llm_reply = call_llm(_budget_prompt(destinations), query)
    cards = [destination_to_card(d) for d in destinations[:2]]
    actions = build_destination_actions(destinations)
    return {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [{"type": "text", "text": llm_reply}],
        "cards": cards,
        "actions": actions,
    }


def _build_weather_response(query: str, destinations: list[dict[str, Any]]) -> dict[str, Any]:
    llm_reply = call_llm(_weather_prompt(destinations), query)
    cards = [destination_to_card(d) for d in destinations[:2]]
    actions = build_destination_actions(destinations)
    return {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [{"type": "text", "text": llm_reply}],
        "cards": cards,
        "actions": actions,
    }


def _no_results_response() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-01",
        "status": "completed",
        "content_parts": [
            {
                "type": "text",
                "text": (
                    "I don't have enough travel context to answer that right now. "
                    "The index may still be loading — try again in a moment, or ask me about "
                    "a specific destination like Paris, Tokyo, Barcelona, or Bali."
                ),
            }
        ],
        "cards": [],
        "actions": [],
    }


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


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _refresh_task

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


app = FastAPI(title="nexo-travel-rag-webhook", lifespan=lifespan)


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
            "schema_version": "2026-03-01",
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
    query: str = message.get("content", "").strip()

    if not query:
        return JSONResponse(
            {
                "schema_version": "2026-03-01",
                "status": "completed",
                "content_parts": [
                    {
                        "type": "text",
                        "text": (
                            "Ask me about travel! I can help you discover destinations, "
                            "plan itineraries, compare budgets, and find the best time to visit "
                            "cities around the world."
                        ),
                    }
                ],
                "cards": [],
                "actions": [],
            }
        )

    intent = detect_intent(query)
    logger.info("Query: %r | Intent: %s", query[:80], intent)

    display_name: str = profile.get("display_name") or profile.get("name") or ""
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
    # SSE streaming path
    # ---------------------------------------------------------------------------

    if wants_stream:

        async def _event_stream() -> AsyncIterator[str]:
            if intent == "itinerary":
                system_prompt = _itinerary_prompt(destinations)
                days_match = re.search(r"\b(\d+)\s*(?:-?\s*)?days?\b", query, re.IGNORECASE)
                num_days = min(int(days_match.group(1)), 7) if days_match else 3
                cards = []
                if destinations:
                    cards.append(destination_to_card(destinations[0]))
                    cards.append(build_itinerary_card(destinations[0], days=num_days))
                actions = build_destination_actions(destinations)
            elif intent == "budget":
                system_prompt = _budget_prompt(destinations)
                cards = [destination_to_card(d) for d in destinations[:2]]
                actions = build_destination_actions(destinations)
            elif intent == "weather":
                system_prompt = _weather_prompt(destinations)
                cards = [destination_to_card(d) for d in destinations[:2]]
                actions = build_destination_actions(destinations)
            else:
                system_prompt = _destination_prompt(destinations, articles)
                cards = [destination_to_card(d) for d in destinations[:3]]
                actions = build_destination_actions(destinations)
                if not actions and articles:
                    actions = build_article_actions(articles)

            prefix = f"Hey {display_name}! " if display_name else ""
            if prefix:
                yield f"data: {json.dumps({'type': 'delta', 'text': prefix})}\n\n"

            async for event in stream_llm(system_prompt, query):
                yield event

            done_payload = json.dumps(
                {
                    "type": "done",
                    "schema_version": "2026-03-01",
                    "status": "completed",
                    "cards": cards,
                    "actions": actions,
                }
            )
            yield f"data: {done_payload}\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    # ---------------------------------------------------------------------------
    # JSON (non-streaming) path
    # ---------------------------------------------------------------------------

    if intent == "itinerary":
        response_body = _build_itinerary_response(query, destinations)
    elif intent == "budget":
        response_body = _build_budget_response(query, destinations)
    elif intent == "weather":
        response_body = _build_weather_response(query, destinations)
    else:
        response_body = _build_destination_response(query, destinations, articles)

    if display_name:
        response_body = _personalise(response_body, display_name)

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
