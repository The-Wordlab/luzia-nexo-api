"""Travel Planning -- Multi-step orchestration webhook for Nexo Partner Agent API.

Demonstrates 3 intents:
- trip_plan: Takes destination + dates + preferences. Returns destination card with
  itinerary, estimated budget breakdown (flights, hotels, activities, food), and
  weather summary. capability_state: "simulated"
- budget_check: Reviews current trip budget. Returns expense tracking card showing
  spent vs budget, alerts if over budget, suggestions to save.
  capability_state: "simulated"
- disruption_replan: Handles flight delay/cancellation scenario. Returns disruption
  alert card + alternative options (rebook, reroute, refund) with approval actions.
  capability_state: "simulated"

Capabilities are simulated (no real travel API required).
"""

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

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
STREAMING_ENABLED = os.environ.get("STREAMING_ENABLED", "true").lower() == "true"

SCHEMA_VERSION = "2026-03-01"
CAPABILITY_NAME = "travel.planning"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-travel-planning",
    "description": "Travel planning webhook example for trip planning, budget checks, and disruption handling.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Guide users through plan creation, spend management, and disruption replan flows.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {"intents": ["trip_plan", "budget_check", "disruption_replan"]},
            }
        ]
    },
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
    "trip_plan": [
        "plan", "trip", "travel", "destination", "itinerary", "going to",
        "visit", "holiday", "vacation", "book", "flights", "hotel", "days",
        "week", "weekend", "where should", "suggest", "recommend",
    ],
    "budget_check": [
        "budget", "cost", "spend", "spent", "expense", "how much", "afford",
        "price", "money", "total", "check budget", "over budget", "savings",
        "save money", "cheaper", "expensive",
    ],
    "disruption_replan": [
        "delay", "delayed", "cancelled", "cancellation", "disruption", "missed",
        "rebook", "reroute", "refund", "alternative", "flight cancelled",
        "stranded", "change flight", "stuck", "emergency", "rebooking",
    ],
}


def detect_intent(message: str) -> str:
    """Detect user intent from message text via keyword counting.

    Priority: disruption_replan > budget_check > trip_plan > trip_plan (default).
    """
    text = message.lower()
    counts: dict[str, int] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        counts[intent] = sum(1 for kw in keywords if kw in text)

    # Priority ordering for tie-breaking
    priority = ["disruption_replan", "budget_check", "trip_plan"]
    best_intent = max(priority, key=lambda k: counts[k])
    if counts[best_intent] > 0:
        return best_intent

    # Default to trip_plan for ambiguous/unknown messages
    return "trip_plan"


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    if intent == "trip_plan":
        return [
            "Show a cheaper destination alternative",
            "Build a day-by-day itinerary",
            "Adjust this plan for a shorter trip",
        ]
    if intent == "budget_check":
        return [
            "Show full budget breakdown",
            "How can I reduce hotel costs?",
            "Update budget to EUR 1200",
        ]
    if intent == "disruption_replan":
        return [
            "Find the fastest rebooking option",
            "What are my refund options?",
            "Create a fallback itinerary",
        ]
    return []


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
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error" if task_status in {"failed", "canceled"} else "completed",
        "task": {"id": f"task_travel_planning_{intent}", "status": task_status},
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": cards or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "metadata": payload_metadata,
    }


# ---------------------------------------------------------------------------
# Simulated travel data
# ---------------------------------------------------------------------------

_DESTINATIONS: dict[str, dict[str, Any]] = {
    "barcelona": {
        "name": "Barcelona, Spain",
        "weather": "Sunny, 22C - ideal for sightseeing",
        "highlights": ["Sagrada Familia", "Park Guell", "Las Ramblas", "Gothic Quarter"],
        "best_months": "April to June, September to November",
    },
    "tokyo": {
        "name": "Tokyo, Japan",
        "weather": "Mild, 18C - cherry blossom season",
        "highlights": ["Shibuya Crossing", "Senso-ji Temple", "Akihabara", "Shinjuku Gyoen"],
        "best_months": "March to May, October to November",
    },
    "lisbon": {
        "name": "Lisbon, Portugal",
        "weather": "Warm, 20C - mostly sunny",
        "highlights": ["Alfama District", "Belem Tower", "Time Out Market", "Sintra day trip"],
        "best_months": "March to May, September to October",
    },
    "default": {
        "name": "Your Destination",
        "weather": "Check local forecast before departure",
        "highlights": ["City centre", "Local markets", "Cultural sites", "Waterfront area"],
        "best_months": "Spring and autumn are generally best for travel",
    },
}

_BUDGET_TEMPLATES: dict[str, dict[str, float]] = {
    "budget": {
        "flights": 250.0,
        "hotels": 60.0,
        "activities": 30.0,
        "food": 25.0,
    },
    "mid-range": {
        "flights": 450.0,
        "hotels": 130.0,
        "activities": 60.0,
        "food": 50.0,
    },
    "luxury": {
        "flights": 900.0,
        "hotels": 320.0,
        "activities": 150.0,
        "food": 100.0,
    },
}

_DISRUPTION_SCENARIOS: list[dict[str, Any]] = [
    {
        "type": "delay",
        "title": "Flight Delay - 3 Hours",
        "severity": "moderate",
        "description": "Your outbound flight BA2490 is delayed by 3 hours due to air traffic control restrictions.",
        "alternatives": [
            {"label": "Wait for original flight", "action": "wait", "note": "Arrives 3 hours late"},
            {"label": "Rebook on next departure", "action": "rebook", "note": "Next available 14:30"},
            {"label": "Request lounge access", "action": "lounge", "note": "Complimentary with delay"},
        ],
    },
    {
        "type": "cancellation",
        "title": "Flight Cancelled",
        "severity": "high",
        "description": "Your return flight TP874 has been cancelled due to operational reasons. Full refund or rebooking available.",
        "alternatives": [
            {"label": "Rebook on next flight", "action": "rebook", "note": "Tomorrow 09:15 - 2 seats left"},
            {"label": "Reroute via connecting city", "action": "reroute", "note": "Via Madrid, arrives +4h"},
            {"label": "Request full refund", "action": "refund", "note": "Processed in 5-7 business days"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


def _get_destination_data(query: str) -> dict[str, Any]:
    """Extract destination from query, return matching destination data."""
    text = query.lower()
    for key, data in _DESTINATIONS.items():
        if key != "default" and key in text:
            return data
    return _DESTINATIONS["default"]


def _get_budget_tier(query: str) -> str:
    """Detect budget tier from query text."""
    text = query.lower()
    if any(w in text for w in ["luxury", "premium", "business class", "5 star", "five star"]):
        return "luxury"
    if any(w in text for w in ["budget", "cheap", "backpack", "hostel", "affordable"]):
        return "budget"
    return "mid-range"


def build_trip_plan_card(destination_data: dict[str, Any], budget: dict[str, float], days: int) -> dict[str, Any]:
    """Build a destination + itinerary card with budget breakdown."""
    nightly_total = budget["hotels"] * days
    per_day_food = budget["food"] * days
    per_day_activities = budget["activities"] * days
    grand_total = budget["flights"] + nightly_total + per_day_food + per_day_activities

    fields: list[dict[str, str]] = [
        {"label": "Destination", "value": destination_data["name"]},
        {"label": "Duration", "value": f"{days} days"},
        {"label": "Weather", "value": destination_data["weather"]},
        {"label": "Top highlights", "value": ", ".join(destination_data["highlights"])},
        {"label": "Best time to visit", "value": destination_data["best_months"]},
        {"label": "Flights (return)", "value": f"~EUR {budget['flights']:.0f}"},
        {"label": "Hotels (per night)", "value": f"~EUR {budget['hotels']:.0f}"},
        {"label": "Activities (per day)", "value": f"~EUR {budget['activities']:.0f}"},
        {"label": "Food (per day)", "value": f"~EUR {budget['food']:.0f}"},
        {"label": "Estimated total", "value": f"~EUR {grand_total:.0f}"},
    ]

    return {
        "type": "trip_plan",
        "title": f"Trip to {destination_data['name']}",
        "subtitle": f"{days}-day itinerary with budget estimate",
        "badges": ["Travel Planning", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_budget_check_card(budget_total: float, spent: float) -> dict[str, Any]:
    """Build an expense tracking card showing spent vs budget."""
    remaining = budget_total - spent
    over_budget = spent > budget_total
    pct_used = min(100, int((spent / budget_total) * 100)) if budget_total > 0 else 0

    status = "Over budget" if over_budget else ("On track" if pct_used < 80 else "Almost at limit")

    fields: list[dict[str, str]] = [
        {"label": "Total budget", "value": f"EUR {budget_total:.2f}"},
        {"label": "Spent so far", "value": f"EUR {spent:.2f}"},
        {"label": "Remaining", "value": f"EUR {remaining:.2f}"},
        {"label": "Usage", "value": f"{pct_used}% of budget used"},
        {"label": "Status", "value": status},
    ]

    if over_budget:
        fields.append({"label": "Saving tip", "value": "Consider cooking one meal a day or switching to public transport"})
    elif pct_used >= 80:
        fields.append({"label": "Saving tip", "value": "Look for free museum days or happy hour deals"})
    else:
        fields.append({"label": "Saving tip", "value": "You are within budget - enjoy a treat!"})

    return {
        "type": "budget_check",
        "title": "Trip Budget Tracker",
        "subtitle": status,
        "badges": ["Travel Planning", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_disruption_card(scenario_index: int = 0) -> dict[str, Any]:
    """Build a disruption alert card with alternative options."""
    idx = min(scenario_index, len(_DISRUPTION_SCENARIOS) - 1)
    scenario = _DISRUPTION_SCENARIOS[idx]

    fields: list[dict[str, str]] = [
        {"label": "Alert type", "value": scenario["title"]},
        {"label": "Severity", "value": scenario["severity"].capitalize()},
        {"label": "Details", "value": scenario["description"]},
    ]

    for i, alt in enumerate(scenario["alternatives"], start=1):
        fields.append({
            "label": f"Option {i}: {alt['label']}",
            "value": alt["note"],
        })

    return {
        "type": "disruption_alert",
        "title": scenario["title"],
        "subtitle": scenario["description"],
        "badges": ["Travel Planning", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    name = profile.get("display_name") or profile.get("name") or ""
    return name.strip()


def _extract_trip_days(query: str) -> int:
    """Extract number of trip days from query text, default to 7."""
    import re
    match = re.search(r"(\d+)\s*(?:day|night|week)", query.lower())
    if match:
        n = int(match.group(1))
        # Convert weeks to days
        if "week" in query[match.start():match.end() + 5].lower():
            return n * 7
        return n
    return 7


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful travel planning assistant. Help users plan trips, manage budgets, and handle travel disruptions. Be concise, friendly, and practical. Keep responses brief - the structured cards show the full details."""


async def call_llm(system_prompt: str, user_message: str) -> str:
    """Non-streaming LLM call."""
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I'm having trouble generating a response right now."


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream LLM response tokens as SSE events."""
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Travel Planning Webhook")


@app.get("/.well-known/agent.json")
async def agent_card():
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root():
    """Service discovery endpoint."""
    return {
        "service": "webhook-travel-planning-python",
        "description": "Travel Planning webhook -- trip planning, budget tracking, disruption replanning.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/.well-known/agent.json", "method": "GET", "description": "Capability discovery metadata"},
            {"path": "/health", "method": "GET", "description": "Health check"},
            {"path": "/ingest", "method": "POST", "description": "Placeholder for future data ingestion"},
        ],
        "capabilities": [
            {"intent": "trip_plan", "state": "simulated"},
            {"intent": "budget_check", "state": "simulated"},
            {"intent": "disruption_replan", "state": "simulated"},
        ],
        "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
        "schema_version": SCHEMA_VERSION,
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "timestamp": time.time(),
    }


@app.post("/ingest")
async def ingest(request: Request):
    """Placeholder for future data ingestion (destination data, pricing updates, etc.)."""
    return {"status": "ok", "message": "Ingest endpoint reserved for future use"}


# ---------------------------------------------------------------------------
# Main webhook endpoint
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

    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    context_block = ""

    if intent == "trip_plan":
        destination_data = _get_destination_data(query)
        budget_tier = _get_budget_tier(query)
        budget = _BUDGET_TEMPLATES[budget_tier]
        days = _extract_trip_days(query)

        cards.append(build_trip_plan_card(destination_data, budget, days))
        context_block = (
            f"Trip plan for {destination_data['name']}:\n"
            f"  Duration: {days} days\n"
            f"  Budget tier: {budget_tier}\n"
            f"  Weather: {destination_data['weather']}\n"
            f"  Highlights: {', '.join(destination_data['highlights'])}\n"
            f"  Estimated flights: EUR {budget['flights']:.0f}\n"
            f"  Hotels per night: EUR {budget['hotels']:.0f}\n"
        )
        actions = [
            {"id": "check_budget", "type": "primary", "label": "Check Budget", "action": "check_budget"},
            {"id": "adjust_preferences", "type": "secondary", "label": "Adjust Preferences", "action": "adjust_preferences"},
            {"id": "see_alternatives", "type": "secondary", "label": "See Alternatives", "action": "see_alternatives"},
        ]
        artifacts = [{"type": "application/json", "name": "trip_plan", "data": {"destination": destination_data, "budget": budget, "days": days}}]

    elif intent == "budget_check":
        # Simulated: 65% spent of a EUR 1500 budget
        budget_total = 1500.0
        spent = 975.0
        cards.append(build_budget_check_card(budget_total, spent))
        context_block = (
            f"Budget check:\n"
            f"  Total budget: EUR {budget_total:.2f}\n"
            f"  Spent so far: EUR {spent:.2f}\n"
            f"  Remaining: EUR {budget_total - spent:.2f}\n"
            f"  Status: On track (65% used)"
        )
        actions = [
            {"id": "view_breakdown", "type": "primary", "label": "View Full Breakdown", "action": "view_breakdown"},
            {"id": "saving_tips", "type": "secondary", "label": "Get Saving Tips", "action": "saving_tips"},
            {"id": "update_budget", "type": "secondary", "label": "Update Budget", "action": "update_budget"},
        ]
        artifacts = [{"type": "application/json", "name": "budget_check", "data": {"budget_total": budget_total, "spent": spent, "remaining": budget_total - spent}}]

    elif intent == "disruption_replan":
        # Default to cancellation scenario for most dramatic demo
        scenario_index = 1 if "cancel" in query.lower() else 0
        cards.append(build_disruption_card(scenario_index=scenario_index))
        scenario = _DISRUPTION_SCENARIOS[scenario_index]
        context_block = (
            f"Travel disruption:\n"
            f"  Type: {scenario['title']}\n"
            f"  Severity: {scenario['severity']}\n"
            f"  Details: {scenario['description']}\n"
            f"  Options: {', '.join(a['label'] for a in scenario['alternatives'])}"
        )
        actions = [
            {"id": "rebook_flight", "type": "primary", "label": "Rebook Flight", "action": "rebook_flight"},
            {"id": "request_refund", "type": "secondary", "label": "Request Refund", "action": "request_refund"},
            {"id": "contact_support", "type": "secondary", "label": "Contact Support", "action": "contact_support"},
        ]
        artifacts = [{"type": "application/json", "name": "disruption", "data": scenario}]

    # Build LLM prompt
    if context_block:
        llm_prompt = f"Context:\n{context_block}\n\nUser message: {query}"
    else:
        llm_prompt = f"User message: {query}"

    system = SYSTEM_PROMPT
    if display_name:
        system += f"\nThe user's name is {display_name}. Address them by name."

    # SSE or JSON
    wants_stream = (
        STREAMING_ENABLED
        and "text/event-stream" in request.headers.get("accept", "")
    )

    if wants_stream:
        prompt_suggestions = prompt_suggestions_for_intent(intent)

        async def _event_stream() -> AsyncIterator[str]:
            yield (
                "event: task.started\ndata: "
                + json.dumps({"task": {"id": f"task_travel_planning_{intent}", "status": "in_progress"}})
                + "\n\n"
            )
            prefix = f"Hey {display_name}! " if display_name else ""
            if prefix:
                yield f"data: {json.dumps({'type': 'delta', 'text': prefix})}\n\n"
                yield f"event: task.delta\ndata: {json.dumps({'text': prefix})}\n\n"

            async for event in stream_llm(system, llm_prompt):
                if event.startswith("data:"):
                    try:
                        payload = json.loads(event[len("data:"):].strip())
                    except json.JSONDecodeError:
                        yield event
                        continue
                    if payload.get("type") == "delta":
                        yield event
                        yield f"event: task.delta\ndata: {json.dumps({'text': payload.get('text', '')})}\n\n"
                        continue
                yield event

            for artifact in artifacts:
                yield f"event: task.artifact\ndata: {json.dumps(artifact)}\n\n"

            done_payload = {
                "type": "done",
                **_build_envelope(
                    text=prefix.strip(),
                    intent=intent,
                    cards=cards,
                    actions=actions,
                    artifacts=artifacts,
                    metadata={"prompt_suggestions": prompt_suggestions},
                ),
            }
            yield f"data: {json.dumps(done_payload)}\n\n"
            yield "event: done\ndata: " + json.dumps(done_payload) + "\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    # Non-streaming JSON
    llm_reply = await call_llm(system, llm_prompt)
    if display_name:
        llm_reply = f"Hey {display_name}! {llm_reply}"

    return JSONResponse(
        _build_envelope(
            text=llm_reply,
            intent=intent,
            cards=cards,
            actions=actions,
            artifacts=artifacts,
        )
    )
