"""Fitness Coach - realistic webhook demo for Nexo Partner Agent API.

Intents:
- workout_plan: create structured weekly plan card
- progress_check: review progress + next targets
- nutrition_guidance: pre/post workout meal guidance

This demo is webhook-backed and deterministic. It uses optional LLM text polish
while keeping structured cards as the primary contract.
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
SCHEMA_VERSION = "2026-03"
CAPABILITY_NAME = "fitness.coach"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-fitness-coach",
    "description": "Fitness coach webhook example for workout plans, progress checks, and nutrition guidance.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Provide practical fitness coaching using structured cards and optional token streaming.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["workout_plan", "progress_check", "nutrition_guidance"],
                    "prompt_suggestions": [
                        "Design a 4-week beginner workout plan",
                        "I just ran 5km in 28 minutes - how am I doing?",
                        "What should I eat before a morning workout?",
                    ],
                },
            }
        ]
    },
}


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


INTENT_KEYWORDS: dict[str, list[str]] = {
    "workout_plan": [
        "workout plan", "training plan", "program", "routine", "strength",
        "beginner", "hypertrophy", "split", "exercise plan", "4-week",
    ],
    "progress_check": [
        "progress", "how am i doing", "improving", "ran", "pace", "pr", "results",
        "plateau", "performance", "check in", "metrics",
    ],
    "nutrition_guidance": [
        "eat", "nutrition", "meal", "protein", "carbs", "before workout",
        "after workout", "snack", "hydration", "diet",
    ],
}


def detect_intent(message: str) -> str:
    text = message.lower()
    counts = {intent: sum(1 for kw in kws if kw in text) for intent, kws in INTENT_KEYWORDS.items()}
    priority = ["progress_check", "nutrition_guidance", "workout_plan"]
    best = max(priority, key=lambda i: counts[i])
    return best if counts[best] > 0 else "workout_plan"


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    suggestions = {
        "workout_plan": [
            "Design a 4-week beginner workout plan",
            "Create a push/pull/legs split for me",
            "Give me a low-impact routine for this week",
        ],
        "progress_check": [
            "I ran 5km in 28 minutes - how am I improving?",
            "Review my progress from the last 2 weeks",
            "Set a realistic target for next month",
        ],
        "nutrition_guidance": [
            "What should I eat before a morning workout?",
            "Give me a post-workout meal idea under 600 calories",
            "How much protein should I target daily?",
        ],
    }
    return suggestions.get(intent, suggestions["workout_plan"])


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
        "task": {"id": f"task_fitness_{intent}", "status": task_status},
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": cards or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "metadata": payload_metadata,
    }


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    name = profile.get("display_name") or profile.get("name") or ""
    return str(name).strip()


def _get_locale(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
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


def _language_instruction(locale: str) -> str:
    if not locale:
        return ""
    return (
        f" Respond in the user's preferred language ({locale}) for all free-form text. "
        "Keep exercise names and metrics readable."
    )


def _extract_level(query: str) -> str:
    text = query.lower()
    if any(k in text for k in ["advanced", "athlete", "experienced"]):
        return "advanced"
    if any(k in text for k in ["intermediate", "some experience"]):
        return "intermediate"
    return "beginner"


def build_workout_plan_card(level: str) -> dict[str, Any]:
    plans = {
        "beginner": [
            "Day 1 - Full body strength (45 min)",
            "Day 2 - Mobility + zone 2 cardio (30 min)",
            "Day 3 - Full body strength (45 min)",
            "Day 4 - Recovery walk + stretching (25 min)",
        ],
        "intermediate": [
            "Day 1 - Upper push + core (60 min)",
            "Day 2 - Lower body strength (55 min)",
            "Day 3 - Upper pull + intervals (60 min)",
            "Day 4 - Lower hypertrophy + mobility (55 min)",
        ],
        "advanced": [
            "Day 1 - Heavy lower + sprint mechanics (75 min)",
            "Day 2 - Upper strength + rowing intervals (70 min)",
            "Day 3 - Active recovery + mobility (40 min)",
            "Day 4 - Full body power + aerobic threshold (75 min)",
            "Day 5 - Hypertrophy accessory + conditioning (65 min)",
        ],
    }
    fields = [{"label": f"Week plan ({level})", "value": " | ".join(plans[level])}]
    fields.append({"label": "Progression", "value": "Increase load 2-5% when reps are completed with good form"})
    return {
        "type": "workout_plan",
        "title": "Your Training Plan",
        "subtitle": "Personalized weekly split",
        "badges": ["Fitness", "Webhook"],
        "fields": fields,
        "metadata": {"capability_state": "live"},
    }


def build_progress_card() -> dict[str, Any]:
    return {
        "type": "progress_check",
        "title": "Performance Snapshot",
        "subtitle": "Last 14 days",
        "badges": ["Fitness", "Webhook"],
        "fields": [
            {"label": "Running pace", "value": "5 km: 29:20 -> 28:00"},
            {"label": "Strength", "value": "Goblet squat: 16 kg -> 20 kg"},
            {"label": "Consistency", "value": "8 sessions completed / 10 planned"},
            {"label": "Next target", "value": "Sub-27:30 5 km in 3 weeks"},
        ],
        "metadata": {"capability_state": "live"},
    }


def build_nutrition_card() -> dict[str, Any]:
    return {
        "type": "nutrition_guidance",
        "title": "Workout Nutrition",
        "subtitle": "Simple fueling plan",
        "badges": ["Fitness", "Webhook"],
        "fields": [
            {"label": "Pre-workout (60-90m)", "value": "Yogurt + banana + oats"},
            {"label": "Post-workout (within 60m)", "value": "30g protein + carbs (rice/potato/fruit)"},
            {"label": "Hydration", "value": "500ml pre-session + 150-250ml every 20 min"},
            {"label": "Daily baseline", "value": "Protein 1.6-2.0 g/kg body weight"},
        ],
        "metadata": {"capability_state": "live"},
    }


SYSTEM_PROMPT = (
    "You are a practical fitness coach. Keep responses concise, actionable, and safe. "
    "Use the structured card context and avoid medical claims."
)


async def call_llm(system_prompt: str, user_message: str) -> str:
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=260,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I prepared a structured fitness recommendation below."


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=260,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
    except Exception as exc:
        logger.warning("LLM stream failed: %s", exc)
        yield f"data: {json.dumps({'type': 'delta', 'text': 'I prepared a structured fitness recommendation below.'})}\n\n"


app = FastAPI(title="Fitness Coach Webhook")


@app.get("/.well-known/agent.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root():
    return {
        "service": "webhook-fitness-coach-python",
        "description": "Fitness coach webhook - workout plans, progress checks, nutrition guidance.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/.well-known/agent.json", "method": "GET", "description": "Capability discovery metadata"},
            {"path": "/health", "method": "GET", "description": "Health check"},
        ],
        "capabilities": [
            {"intent": "workout_plan", "state": "live"},
            {"intent": "progress_check", "state": "live"},
            {"intent": "nutrition_guidance", "state": "live"},
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
    display_name = _get_display_name(data)
    locale = _get_locale(data)

    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    context_block = ""

    if intent == "workout_plan":
        level = _extract_level(query)
        cards.append(build_workout_plan_card(level))
        context_block = f"Goal: workout plan. Level: {level}."
        artifacts = [{"type": "application/json", "name": "workout_plan", "data": {"level": level}}]
        actions = [
            {"id": "start_week", "type": "primary", "label": "Start This Week", "action": "start_week"},
            {"id": "adjust_level", "type": "secondary", "label": "Adjust Level", "action": "adjust_level"},
        ]
    elif intent == "progress_check":
        cards.append(build_progress_card())
        context_block = "Goal: progress review and next targets."
        artifacts = [{"type": "application/json", "name": "progress_snapshot", "data": {"period_days": 14}}]
        actions = [
            {"id": "set_target", "type": "primary", "label": "Set Next Target", "action": "set_target"},
            {"id": "weekly_checkin", "type": "secondary", "label": "Weekly Check-in", "action": "weekly_checkin"},
        ]
    else:
        cards.append(build_nutrition_card())
        context_block = "Goal: fueling guidance around workouts."
        artifacts = [{"type": "application/json", "name": "nutrition_guidance", "data": {"focus": "workout"}}]
        actions = [
            {"id": "build_meal_plan", "type": "primary", "label": "Build Meal Plan", "action": "build_meal_plan"},
            {"id": "swap_options", "type": "secondary", "label": "Swap Options", "action": "swap_options"},
        ]

    llm_prompt = f"Context:\n{context_block}\n\nUser message: {query}"
    system = SYSTEM_PROMPT + (f" The user's name is {display_name}." if display_name else "") + _language_instruction(locale)

    wants_stream = STREAMING_ENABLED and "text/event-stream" in request.headers.get("accept", "")
    if wants_stream:

        async def _event_stream() -> AsyncIterator[str]:
            yield (
                "event: task.started\ndata: "
                + json.dumps({"task": {"id": f"task_fitness_{intent}", "status": "in_progress"}})
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
                ),
            }
            yield f"data: {json.dumps(done_payload)}\n\n"
            yield "event: done\ndata: " + json.dumps(done_payload) + "\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    reply = await call_llm(system, llm_prompt)
    prefix = _localized_prefix(locale, display_name)
    if prefix:
        reply = f"{prefix}{reply}"
    return JSONResponse(
        _build_envelope(
            text=reply,
            intent=intent,
            cards=cards,
            actions=actions,
            artifacts=artifacts,
        )
    )
