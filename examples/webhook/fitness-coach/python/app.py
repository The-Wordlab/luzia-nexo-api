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


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    name = profile.get("display_name") or profile.get("name") or ""
    return str(name).strip()


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


@app.get("/")
async def root():
    return {
        "service": "webhook-fitness-coach-python",
        "description": "Fitness coach webhook - workout plans, progress checks, nutrition guidance.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
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

    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    context_block = ""

    if intent == "workout_plan":
        level = _extract_level(query)
        cards.append(build_workout_plan_card(level))
        context_block = f"Goal: workout plan. Level: {level}."
        actions = [
            {"id": "start_week", "type": "primary", "label": "Start This Week", "action": "start_week"},
            {"id": "adjust_level", "type": "secondary", "label": "Adjust Level", "action": "adjust_level"},
        ]
    elif intent == "progress_check":
        cards.append(build_progress_card())
        context_block = "Goal: progress review and next targets."
        actions = [
            {"id": "set_target", "type": "primary", "label": "Set Next Target", "action": "set_target"},
            {"id": "weekly_checkin", "type": "secondary", "label": "Weekly Check-in", "action": "weekly_checkin"},
        ]
    else:
        cards.append(build_nutrition_card())
        context_block = "Goal: fueling guidance around workouts."
        actions = [
            {"id": "build_meal_plan", "type": "primary", "label": "Build Meal Plan", "action": "build_meal_plan"},
            {"id": "swap_options", "type": "secondary", "label": "Swap Options", "action": "swap_options"},
        ]

    llm_prompt = f"Context:\n{context_block}\n\nUser message: {query}"
    system = SYSTEM_PROMPT + (f" The user's name is {display_name}." if display_name else "")

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
                "cards": cards,
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
            "cards": cards,
            "actions": actions,
        }
    )
