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

SCHEMA_VERSION = "2026-03"
CAPABILITY_NAME = "routines.daily"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-routines",
    "description": "Daily routines webhook example for briefings, schedule, and follow-up actions.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Assist with morning planning, schedule management, and follow-ups.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["morning_briefing", "schedule_management", "follow_up"],
                    "prompt_suggestions": [
                        "Give me my morning briefing",
                        "What meetings do I have today?",
                        "Summarize my pending tasks",
                    ],
                },
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


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    if intent == "morning_briefing":
        return [
            "Summarize my top priorities",
            "What should I tackle first today?",
            "Help me plan a 2-hour focus block",
        ]
    if intent == "schedule_management":
        return [
            "Show my next meeting",
            "Find a free 30-minute slot this afternoon",
            "Add a reminder for tomorrow morning",
        ]
    if intent == "follow_up":
        return [
            "Show high-priority tasks first",
            "Draft a follow-up message for this task",
            "Snooze non-urgent items to tomorrow",
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
        "task": {"id": f"task_routines_{intent}", "status": task_status},
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": cards or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "metadata": payload_metadata,
    }


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


def build_morning_briefing_card(
    display_name: str,
    *,
    locale: str = "",
    personal_focus: str | None = None,
) -> dict[str, Any]:
    """Build a morning_briefing card with weather, calendar summary, and priorities."""
    greeting = _localized_morning_greeting(locale, display_name)
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
    if personal_focus:
        fields.append({"label": "Personal focus", "value": personal_focus})
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


def _get_profile(data: dict[str, Any]) -> dict[str, Any]:
    profile = data.get("profile") or {}
    return profile if isinstance(profile, dict) else {}


def _get_preferences(data: dict[str, Any]) -> dict[str, Any]:
    preferences = _get_profile(data).get("preferences") or {}
    return preferences if isinstance(preferences, dict) else {}


def _get_locale(data: dict[str, Any]) -> str:
    profile = _get_profile(data)
    locale = profile.get("locale") or profile.get("language") or _get_preferences(data).get("language") or ""
    return str(locale).strip()


def _build_personal_focus(data: dict[str, Any]) -> str | None:
    preferences = _get_preferences(data)
    profile = _get_profile(data)
    facts = profile.get("facts") or []
    if not isinstance(facts, list):
        facts = []

    focus_parts: list[str] = []
    dietary = preferences.get("dietary")
    if dietary == "vegetarian":
        focus_parts.append("keep a plant-based lunch in the plan")
    elif dietary:
        focus_parts.append(f"make room for {dietary} meal options")

    dining_style = preferences.get("dining_style")
    if dining_style == "family":
        focus_parts.append("leave time to coordinate dinner for the family")
    elif dining_style == "quick":
        focus_parts.append("keep meals and errands efficient")

    budget = preferences.get("budget")
    if budget == "low":
        focus_parts.append("keep meals and errands budget-conscious")
    elif budget == "high":
        focus_parts.append("protect time for premium reservations and planning")

    lowered_facts = [str(f).lower() for f in facts if isinstance(f, str)]
    if any(
        "work out" in fact or "workout" in fact or "works out" in fact
        for fact in lowered_facts
    ):
        focus_parts.append("protect a workout block")

    if not focus_parts:
        return None
    return "; ".join(focus_parts)


def _build_personalization_metadata(data: dict[str, Any]) -> dict[str, Any]:
    used: dict[str, Any] = {}
    locale = _get_locale(data)
    personal_focus = _build_personal_focus(data)
    if locale:
        used["locale"] = locale
    if personal_focus:
        used["routine_focus"] = personal_focus
    return {
        "mode": "profile" if used else "generic",
        "used": used,
        "missing_optional": [key for key in ["locale", "routine_focus"] if key not in used],
    }


def _localized_morning_greeting(locale: str, display_name: str) -> str:
    greeting = "Good morning"
    if locale.startswith("pt"):
        greeting = "Bom dia"
    elif locale.startswith("fr"):
        greeting = "Bonjour"
    elif locale.startswith("ja"):
        greeting = "Ohayo"
    return f"{greeting}, {display_name}!" if display_name else f"{greeting}!"


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


def _language_instruction(locale: str) -> str:
    if not locale:
        return ""
    return (
        f"\nRespond in the user's preferred language ({locale}) for all free-form text. "
        "Keep schedule times and structured fields easy to scan."
    )


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


@app.get("/.well-known/agent.json")
async def agent_card():
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root():
    """Service discovery endpoint."""
    return {
        "service": "webhook-routines-python",
        "description": "Daily Routines webhook — morning briefing, schedule management, follow-up reminders.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/.well-known/agent.json", "method": "GET", "description": "Capability discovery metadata"},
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
    locale = _get_locale(data)
    personal_focus = _build_personal_focus(data)
    personalization = _build_personalization_metadata(data)

    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    context_block = ""

    if intent == "morning_briefing":
        cards.append(
            build_morning_briefing_card(
                display_name,
                locale=locale,
                personal_focus=personal_focus,
            )
        )
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
        if personal_focus:
            context_block += f"\nPersonal focus:\n  - {personal_focus}"
        actions = [
            {"id": "show_schedule", "type": "primary", "label": "View Schedule", "action": "show_schedule"},
            {"id": "show_reminders", "type": "secondary", "label": "Set a Reminder", "action": "show_reminders"},
        ]
        artifacts = [{"type": "application/json", "name": "morning_context", "data": {"weather": _SEED_WEATHER, "schedule": _SEED_SCHEDULE, "priorities": _SEED_PRIORITIES}}]

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
        artifacts = [{"type": "application/json", "name": "schedule", "data": _SEED_SCHEDULE}]

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
        artifacts = [{"type": "application/json", "name": "action_items", "data": _SEED_ACTION_ITEMS}]

    # Build LLM prompt
    if context_block:
        llm_prompt = f"Context:\n{context_block}\n\nUser message: {query}"
    else:
        llm_prompt = f"User message: {query}"

    system = SYSTEM_PROMPT
    if display_name:
        system += f"\nThe user's name is {display_name}. Address them by name."
    if locale:
        system += f"\nThe user's locale is {locale}. Match tone and greeting naturally."
    system += _language_instruction(locale)
    if personal_focus:
        system += f"\nUse this saved routine context when relevant: {personal_focus}."

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
                + json.dumps({"task": {"id": f"task_routines_{intent}", "status": "in_progress"}})
                + "\n\n"
            )
            prefix = _localized_prefix(locale, display_name)
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
                    metadata={
                        "prompt_suggestions": prompt_suggestions,
                        "personalization": personalization,
                    },
                ),
            }
            yield f"data: {json.dumps(done_payload)}\n\n"
            yield "event: done\ndata: " + json.dumps(done_payload) + "\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    # Non-streaming JSON
    llm_reply = await call_llm(system, llm_prompt)
    prefix = _localized_prefix(locale, display_name)
    if prefix:
        llm_reply = f"{prefix}{llm_reply}"

    return JSONResponse(
        _build_envelope(
            text=llm_reply,
            intent=intent,
            cards=cards,
            actions=actions,
            artifacts=artifacts,
            metadata={"personalization": personalization},
        )
    )
