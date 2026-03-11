"""Travel Planner - webhook-backed planning demo for Nexo."""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import os
import time
from typing import Any, AsyncIterator

import litellm
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _configure_vertex_env_defaults() -> None:
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

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
STREAMING_ENABLED = os.environ.get("STREAMING_ENABLED", "true").lower() == "true"
SCHEMA_VERSION = "2026-03-01"


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
    ts = request.headers.get("x-timestamp", "")
    sig = request.headers.get("x-signature", "")
    if not _verify_signature(WEBHOOK_SECRET, raw_body, ts, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")


INTENT_KEYWORDS: dict[str, list[str]] = {
    "itinerary": [
        "itinerary", "plan", "trip", "days", "weekend", "must-see", "romantic",
    ],
    "flight_compare": [
        "compare flights", "flights", "cheapest", "price", "depart", "return",
    ],
    "booking_handoff": [
        "book", "reserve", "hotel", "checkout", "confirm booking", "handoff",
    ],
}


def detect_intent(message: str) -> str:
    text = message.lower()
    counts = {k: sum(1 for kw in kws if kw in text) for k, kws in INTENT_KEYWORDS.items()}
    priority = ["booking_handoff", "flight_compare", "itinerary"]
    best = max(priority, key=lambda i: counts[i])
    return best if counts[best] > 0 else "itinerary"


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    return str(profile.get("display_name") or profile.get("name") or "").strip()


def _extract_destination(query: str) -> str:
    lowered = query.lower()
    for city in ["barcelona", "tokyo", "lisbon", "paris", "rome"]:
        if city in lowered:
            return city.title()
    return "Barcelona"


def build_itinerary_card(destination: str, days: int) -> dict[str, Any]:
    return {
        "type": "itinerary",
        "title": f"{destination} in {days} days",
        "subtitle": "Draft plan with pacing and budget",
        "badges": ["Travel", "Webhook"],
        "fields": [
            {"label": "Day 1", "value": "City center orientation + local food walk"},
            {"label": "Day 2", "value": "Top landmarks + neighborhood evening"},
            {"label": "Day 3", "value": "Culture block + flexible free slot"},
            {"label": "Budget", "value": "~EUR 140/day (mid-range)"},
        ],
        "metadata": {"capability_state": "live"},
    }


def build_flights_card(destination: str) -> dict[str, Any]:
    return {
        "type": "flight_compare",
        "title": "Flight Options",
        "subtitle": f"Sample options to {destination}",
        "badges": ["Travel", "Webhook"],
        "fields": [
            {"label": "Option A", "value": "Direct - EUR 220 - 2h40"},
            {"label": "Option B", "value": "1 stop - EUR 170 - 4h10"},
            {"label": "Option C", "value": "Evening direct - EUR 205 - 2h45"},
        ],
        "metadata": {"capability_state": "live"},
    }


def build_booking_card(destination: str) -> dict[str, Any]:
    return {
        "type": "booking_handoff",
        "title": "Ready to Book",
        "subtitle": f"Booking handoff package for {destination}",
        "badges": ["Travel", "Requires Connector"],
        "fields": [
            {"label": "Hotel shortlist", "value": "3 stays near city center"},
            {"label": "Transport", "value": "Airport transfer + local transit pass"},
            {"label": "Handoff", "value": "Approve to continue in partner booking flow"},
        ],
        "metadata": {"capability_state": "requires_connector"},
    }


SYSTEM_PROMPT = "You are a practical travel planner. Keep response concise and grounded in the cards."


async def call_llm(system_prompt: str, user_message: str) -> str:
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=240,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I prepared a structured travel recommendation below."


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=240,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
    except Exception as exc:
        logger.warning("LLM stream failed: %s", exc)
        yield f"data: {json.dumps({'type': 'delta', 'text': 'I prepared a structured travel recommendation below.'})}\n\n"


app = FastAPI(title="Travel Planner Webhook")


@app.get("/")
async def root():
    return {
        "service": "webhook-travel-planner-python",
        "description": "Travel planner webhook - itinerary, flight comparison, booking handoff.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/health", "method": "GET", "description": "Health check"},
        ],
        "capabilities": [
            {"intent": "itinerary", "state": "live"},
            {"intent": "flight_compare", "state": "live"},
            {"intent": "booking_handoff", "state": "requires_connector"},
        ],
        "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
        "schema_version": SCHEMA_VERSION,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


@app.post("/")
async def webhook(request: Request):
    raw = await request.body()
    _require_signature(request, raw)

    data = json.loads(raw)
    query = (data.get("message") or {}).get("content", "")
    if not query:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    intent = detect_intent(query)
    destination = _extract_destination(query)
    days = 3 if "3 day" in query.lower() else 4 if "weekend" in query.lower() else 5
    display_name = _get_display_name(data)

    if intent == "itinerary":
        card = build_itinerary_card(destination, days)
        actions = [
            {"id": "adjust_plan", "type": "primary", "label": "Adjust Plan", "action": "adjust_plan"},
            {"id": "show_budget", "type": "secondary", "label": "Show Budget Split", "action": "show_budget"},
        ]
        context = f"Destination: {destination}. Duration: {days} days."
    elif intent == "flight_compare":
        card = build_flights_card(destination)
        actions = [
            {"id": "pick_option", "type": "primary", "label": "Pick Option", "action": "pick_option"},
            {"id": "set_price_watch", "type": "secondary", "label": "Set Price Watch", "action": "set_price_watch"},
        ]
        context = f"Compare flight options to {destination}."
    else:
        card = build_booking_card(destination)
        actions = [
            {"id": "approve_handoff", "type": "primary", "label": "Approve Booking Handoff", "action": "approve_handoff"},
            {"id": "change_constraints", "type": "secondary", "label": "Change Constraints", "action": "change_constraints"},
        ]
        context = f"Prepare booking handoff for {destination}."

    llm_prompt = f"Context:\n{context}\n\nUser message: {query}"
    system = SYSTEM_PROMPT + (f" User name: {display_name}." if display_name else "")

    wants_stream = STREAMING_ENABLED and "text/event-stream" in request.headers.get("accept", "")
    if wants_stream:

        async def _event_stream() -> AsyncIterator[str]:
            if display_name:
                yield f"data: {json.dumps({'type': 'delta', 'text': f'Hey {display_name}! '})}\n\n"
            async for event in stream_llm(system, llm_prompt):
                yield event
            done = {
                "type": "done",
                "schema_version": SCHEMA_VERSION,
                "status": "completed",
                "cards": [card],
                "actions": actions,
            }
            yield f"data: {json.dumps(done)}\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    reply = await call_llm(system, llm_prompt)
    if display_name:
        reply = f"Hey {display_name}! {reply}"
    return JSONResponse(
        {
            "schema_version": SCHEMA_VERSION,
            "status": "completed",
            "content_parts": [{"type": "text", "text": reply}],
            "cards": [card],
            "actions": actions,
        }
    )
