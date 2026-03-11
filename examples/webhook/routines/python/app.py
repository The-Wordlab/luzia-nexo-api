"""Daily Routines — Multi-step orchestration webhook for Nexo Partner Agent API.

Demonstrates 3 intents:
- morning_briefing: structured briefing card (weather placeholder, calendar, priorities)
- schedule_management: schedule card with time slots
- follow_up: action items card with snooze/complete actions

Capabilities are simulated (no real calendar/weather APIs required).
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
    "morning_briefing": [
        "morning", "briefing", "daily briefing", "good morning",
        "start my day", "day ahead", "today's plan", "wake up",
    ],
    "schedule_management": [
        "schedule", "calendar", "meeting", "appointment", "add to",
        "book", "reschedule", "cancel", "block time", "slot",
        "when is", "what's on",
    ],
    "follow_up": [
        "reminder", "remind", "follow up", "follow-up", "action item",
        "todo", "to-do", "task", "snooze", "don't forget", "check in",
        "circle back",
    ],
}


def detect_intent(message: str) -> str:
    """Detect user intent from message text via keyword counting.

    Priority: schedule_management > follow_up > morning_briefing > morning_briefing (default).
    """
    text = message.lower()
    counts: dict[str, int] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        counts[intent] = sum(1 for kw in keywords if kw in text)

    best_intent = max(counts, key=lambda k: counts[k])
    if counts[best_intent] > 0:
        return best_intent

    # Default to morning_briefing for ambiguous/unknown messages
    return "morning_briefing"


# ---------------------------------------------------------------------------
# Simulated data
# ---------------------------------------------------------------------------

_SEED_PRIORITIES = [
    "Review pull request for authentication module",
    "Prepare slides for 3pm product review",
    "Send status update to stakeholders",
]

_SEED_SCHEDULE = [
    {"time": "09:00", "title": "Team standup", "duration": "30m"},
    {"time": "11:00", "title": "Design review with product", "duration": "1h"},
    {"time": "15:00", "title": "Product review presentation", "duration": "1h"},
    {"time": "17:00", "title": "1:1 with manager", "duration": "30m"},
]

_SEED_ACTION_ITEMS = [
    {"task": "Send recap email from morning standup", "due": "Today, EOD", "priority": "high"},
    {"task": "Review and merge open PRs", "due": "Today", "priority": "medium"},
    {"task": "Update project tracker with this week's progress", "due": "Friday", "priority": "low"},
]

_SEED_WEATHER = {"condition": "Partly cloudy", "temp_c": 18, "temp_f": 64}

# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


def build_morning_briefing_card(display_name: str) -> dict[str, Any]:
    """Build a morning_briefing card with weather, calendar summary, and priorities."""
    greeting = f"Good morning, {display_name}!" if display_name else "Good morning!"
    fields: list[dict[str, str]] = [
        {
            "label": "Weather",
            "value": f"{_SEED_WEATHER['condition']}, {_SEED_WEATHER['temp_c']}°C / {_SEED_WEATHER['temp_f']}°F",
        },
        {
            "label": "Meetings today",
            "value": f"{len(_SEED_SCHEDULE)} scheduled ({_SEED_SCHEDULE[0]['time']}–{_SEED_SCHEDULE[-1]['time']})",
        },
        {
            "label": "Top priorities",
            "value": " · ".join(f"#{i + 1} {p}" for i, p in enumerate(_SEED_PRIORITIES[:2])),
        },
    ]
    return {
        "type": "morning_briefing",
        "title": greeting,
        "subtitle": "Your daily overview",
        "badges": ["Daily Routines", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_schedule_card(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a schedule card with time slots."""
    slots = items if items else _SEED_SCHEDULE
    fields: list[dict[str, str]] = []
    for slot in slots:
        label = slot.get("time", "")
        value = slot.get("title", "No title")
        if slot.get("duration"):
            value += f" ({slot['duration']})"
        fields.append({"label": label, "value": value})

    if not fields:
        fields = [{"label": "No events", "value": "Your calendar is clear today"}]

    return {
        "type": "schedule",
        "title": "Today's Schedule",
        "subtitle": "Your upcoming events",
        "badges": ["Calendar", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_action_items_card(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an action_items card with tasks and due dates."""
    tasks = items if items else _SEED_ACTION_ITEMS
    fields: list[dict[str, str]] = []
    for task in tasks:
        label = task.get("task", "Task")
        priority = task.get("priority", "")
        due = task.get("due", "")
        value_parts = []
        if due:
            value_parts.append(f"Due: {due}")
        if priority:
            value_parts.append(f"Priority: {priority}")
        fields.append({"label": label, "value": " · ".join(value_parts) if value_parts else "Pending"})

    if not fields:
        fields = [{"label": "No action items", "value": "You're all caught up!"}]

    return {
        "type": "action_items",
        "title": "Action Items",
        "subtitle": "Tasks requiring your attention",
        "badges": ["Follow-up", "Simulated"],
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


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful daily routines assistant. Help users plan their day, manage their schedule, and stay on top of their tasks. Be concise, warm, and actionable. Use the structured data provided to give accurate, helpful responses. Do not make up events or tasks beyond what is shown in the context."""


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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Daily Routines Webhook")


@app.get("/")
async def root():
    """Service discovery endpoint."""
    return {
        "service": "webhook-routines-python",
        "description": "Daily Routines webhook — morning briefing, schedule management, follow-up reminders.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/health", "method": "GET", "description": "Health check"},
            {"path": "/ingest", "method": "POST", "description": "Placeholder for future data ingestion"},
        ],
        "capabilities": [
            {"intent": "morning_briefing", "state": "simulated"},
            {"intent": "schedule_management", "state": "simulated"},
            {"intent": "follow_up", "state": "simulated"},
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
    """Placeholder for future data ingestion (calendar events, task lists, etc.)."""
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
    context_block = ""

    if intent == "morning_briefing":
        cards.append(build_morning_briefing_card(display_name))
        # Include schedule overview in context
        schedule_summary = "\n".join(
            f"  {s['time']} — {s['title']} ({s.get('duration', '')})" for s in _SEED_SCHEDULE
        )
        priorities_summary = "\n".join(f"  - {p}" for p in _SEED_PRIORITIES)
        context_block = (
            f"Weather: {_SEED_WEATHER['condition']}, {_SEED_WEATHER['temp_c']}°C\n"
            f"Today's meetings:\n{schedule_summary}\n"
            f"Top priorities:\n{priorities_summary}"
        )
        actions = [
            {"id": "show_schedule", "type": "primary", "label": "View Schedule", "action": "show_schedule"},
            {"id": "show_reminders", "type": "secondary", "label": "Set a Reminder", "action": "show_reminders"},
        ]

    elif intent == "schedule_management":
        cards.append(build_schedule_card(_SEED_SCHEDULE))
        schedule_summary = "\n".join(
            f"  {s['time']} — {s['title']} ({s.get('duration', '')})" for s in _SEED_SCHEDULE
        )
        context_block = f"Today's schedule:\n{schedule_summary}"
        actions = [
            {"id": "add_event", "type": "primary", "label": "Add Event", "action": "add_event"},
            {"id": "show_briefing", "type": "secondary", "label": "Morning Briefing", "action": "show_briefing"},
        ]

    elif intent == "follow_up":
        cards.append(build_action_items_card(_SEED_ACTION_ITEMS))
        tasks_summary = "\n".join(
            f"  - {t['task']} (due: {t.get('due', 'TBD')}, priority: {t.get('priority', 'medium')})"
            for t in _SEED_ACTION_ITEMS
        )
        context_block = f"Action items:\n{tasks_summary}"
        actions = [
            {"id": "mark_complete", "type": "primary", "label": "Mark Done", "action": "mark_complete"},
            {"id": "snooze_reminder", "type": "secondary", "label": "Snooze 1h", "action": "snooze_reminder"},
            {"id": "remind_tomorrow", "type": "secondary", "label": "Remind Tomorrow", "action": "remind_tomorrow"},
        ]

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

    # Non-streaming JSON
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
