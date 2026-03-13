"""Language Tutor - webhook-backed coaching demo for Nexo."""

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
CAPABILITY_NAME = "language.tutor"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-language-tutor",
    "description": "Language tutor webhook example for phrase help, quizzes, and lesson plans.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Support language learning flows with practical cards and optional streaming responses.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["phrase_help", "quiz", "lesson_plan"],
                    "prompt_suggestions": [
                        "Teach me how to order food in Italian",
                        "Give me a quick Spanish conversation quiz",
                        "How do I introduce myself in Portuguese?",
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
    ts = request.headers.get("x-timestamp", "")
    sig = request.headers.get("x-signature", "")
    if not _verify_signature(WEBHOOK_SECRET, raw_body, ts, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")


INTENT_KEYWORDS: dict[str, list[str]] = {
    "phrase_help": [
        "how do i", "teach me", "say", "order food", "introduce myself", "phrase",
    ],
    "quiz": [
        "quiz", "test me", "practice", "conversation quiz", "quick quiz"],
    "lesson_plan": [
        "lesson", "study plan", "weekly plan", "beginner", "learn", "curriculum"],
}


def detect_intent(message: str) -> str:
    text = message.lower()
    counts = {k: sum(1 for kw in kws if kw in text) for k, kws in INTENT_KEYWORDS.items()}
    priority = ["quiz", "phrase_help", "lesson_plan"]
    best = max(priority, key=lambda i: counts[i])
    return best if counts[best] > 0 else "phrase_help"


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    suggestions = {
        "phrase_help": [
            "Teach me how to order food in Italian",
            "How do I introduce myself in Portuguese?",
            "Give me 3 polite Spanish phrases for travel",
        ],
        "quiz": [
            "Give me a quick Spanish conversation quiz",
            "Test me on beginner Italian phrases",
            "Run a short Portuguese pronunciation check",
        ],
        "lesson_plan": [
            "Create a 4-week beginner Spanish plan",
            "Build me a weekly Italian study routine",
            "What should I practice every day for Portuguese?",
        ],
    }
    return suggestions.get(intent, suggestions["phrase_help"])


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
        "task": {"id": f"task_language_tutor_{intent}", "status": task_status},
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": cards or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "metadata": payload_metadata,
    }


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    return str(profile.get("display_name") or profile.get("name") or "").strip()


def _detect_language(query: str) -> str:
    t = query.lower()
    if "italian" in t:
        return "Italian"
    if "spanish" in t:
        return "Spanish"
    if "portuguese" in t:
        return "Portuguese"
    return "Spanish"


def build_phrase_card(language: str) -> dict[str, Any]:
    samples = {
        "Italian": "Vorrei ordinare la pasta, per favore.",
        "Spanish": "Quisiera pedir la cena, por favor.",
        "Portuguese": "Gostaria de pedir o jantar, por favor.",
    }
    return {
        "type": "phrase_help",
        "title": f"{language} Useful Phrase",
        "subtitle": "Restaurant scenario",
        "badges": ["Language", "Webhook"],
        "fields": [
            {"label": "Phrase", "value": samples.get(language, samples["Spanish"])},
            {"label": "Pronunciation", "value": "Tap-to-practice in your app experience"},
            {"label": "Follow-up", "value": "Ask for 3 variations for formal/casual tone"},
        ],
        "metadata": {"capability_state": "live"},
    }


def build_quiz_card(language: str) -> dict[str, Any]:
    return {
        "type": "quiz",
        "title": f"{language} Quick Quiz",
        "subtitle": "2-turn confidence check",
        "badges": ["Language", "Webhook"],
        "fields": [
            {"label": "Prompt 1", "value": "How would you greet a waiter politely?"},
            {"label": "Prompt 2", "value": "Ask for the bill in one sentence."},
            {"label": "Scoring", "value": "Focus on clarity, grammar, and natural phrasing"},
        ],
        "metadata": {"capability_state": "live"},
    }


def build_lesson_card(language: str) -> dict[str, Any]:
    return {
        "type": "lesson_plan",
        "title": f"{language} 4-Week Plan",
        "subtitle": "Beginner progression",
        "badges": ["Language", "Webhook"],
        "fields": [
            {"label": "Week 1", "value": "Survival phrases + pronunciation drills"},
            {"label": "Week 2", "value": "Present tense verbs + food vocabulary"},
            {"label": "Week 3", "value": "Role-play dialogues + correction loop"},
            {"label": "Week 4", "value": "Real-world scenarios + confidence check"},
        ],
        "metadata": {"capability_state": "live"},
    }


SYSTEM_PROMPT = "You are a concise language tutor. Keep output practical and aligned with the card context."


async def call_llm(system_prompt: str, user_message: str) -> str:
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=220,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I prepared a structured language coaching step below."


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=220,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
    except Exception as exc:
        logger.warning("LLM stream failed: %s", exc)
        yield f"data: {json.dumps({'type': 'delta', 'text': 'I prepared a structured language coaching step below.'})}\n\n"


app = FastAPI(title="Language Tutor Webhook")


@app.get("/.well-known/agent.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root():
    return {
        "service": "webhook-language-tutor-python",
        "description": "Language tutor webhook - phrase help, quizzes, and lesson plans.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/.well-known/agent.json", "method": "GET", "description": "Capability discovery metadata"},
            {"path": "/health", "method": "GET", "description": "Health check"},
        ],
        "capabilities": [
            {"intent": "phrase_help", "state": "live"},
            {"intent": "quiz", "state": "live"},
            {"intent": "lesson_plan", "state": "live"},
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
    language = _detect_language(query)
    display_name = _get_display_name(data)

    if intent == "quiz":
        card = build_quiz_card(language)
        artifacts = [{"type": "application/json", "name": "quiz", "data": {"language": language}}]
        actions = [
            {"id": "start_quiz", "type": "primary", "label": "Start Quiz", "action": "start_quiz"},
            {"id": "show_answers", "type": "secondary", "label": "Show Model Answers", "action": "show_answers"},
        ]
        context = f"Language: {language}. Mode: quiz."
    elif intent == "lesson_plan":
        card = build_lesson_card(language)
        artifacts = [{"type": "application/json", "name": "lesson_plan", "data": {"language": language, "weeks": 4}}]
        actions = [
            {"id": "begin_week1", "type": "primary", "label": "Begin Week 1", "action": "begin_week1"},
            {"id": "adapt_level", "type": "secondary", "label": "Adapt Difficulty", "action": "adapt_level"},
        ]
        context = f"Language: {language}. Mode: lesson plan."
    else:
        card = build_phrase_card(language)
        artifacts = [{"type": "application/json", "name": "phrase_help", "data": {"language": language}}]
        actions = [
            {"id": "practice", "type": "primary", "label": "Practice Phrase", "action": "practice"},
            {"id": "more_variants", "type": "secondary", "label": "More Variants", "action": "more_variants"},
        ]
        context = f"Language: {language}. Mode: phrase help."

    llm_prompt = f"Context:\n{context}\n\nUser message: {query}"
    system = SYSTEM_PROMPT + (f" User name: {display_name}." if display_name else "")

    wants_stream = STREAMING_ENABLED and "text/event-stream" in request.headers.get("accept", "")
    if wants_stream:

        async def _event_stream() -> AsyncIterator[str]:
            yield (
                "event: task.started\ndata: "
                + json.dumps({"task": {"id": f"task_language_tutor_{intent}", "status": "in_progress"}})
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
                    cards=[card],
                    actions=actions,
                    artifacts=artifacts,
                ),
            }
            yield f"data: {json.dumps(done_payload)}\n\n"
            yield "event: done\ndata: " + json.dumps(done_payload) + "\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    reply = await call_llm(system, llm_prompt)
    if display_name:
        reply = f"Hey {display_name}! {reply}"
    return JSONResponse(
        _build_envelope(
            text=reply,
            intent=intent,
            cards=[card],
            actions=actions,
            artifacts=artifacts,
        )
    )
