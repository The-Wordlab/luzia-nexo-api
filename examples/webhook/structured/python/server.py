#!/usr/bin/env python3
"""
Intermediate webhook server.

Demonstrates three concepts beyond webhook-basics:

1. Profile-aware personalisation
   Reads profile.name and profile.locale from the incoming payload and
   tailors the reply text accordingly. This mirrors the real Nexo webhook
   contract where every POST includes a ``profile`` object.

2. Locale-aware greetings
   When profile.locale is a supported language code (es, fr, pt, it) the
   server greets the user in that language. Unknown locales fall back to
   English.

3. Card hints
   When the optional ``context`` field signals a specific intent the server
   attaches structured ``cards`` in the response. Partners
   can use this pattern to attach inline cards (suggestions, product
   carousels, consent prompts) alongside the plain-text reply.

Contract:
  POST /   with JSON body {
               "message": {"content": "..."},
               "profile": {"name": "...", "locale": "..."},   # optional
               "context": {"intent": "..."}                    # optional
           }
  ->       {
               "schema_version": "2026-03",
               "status": "completed",
               "content_parts": [{"type": "text", "text": "<personalised text>"}],
               "cards": [...]  # optional
           }
"""

import hashlib
import hmac
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="intermediate-webhook")


@app.get("/")
async def root() -> JSONResponse:
    """Service discovery endpoint for local/manual testing."""
    return JSONResponse(
        {
            "service": "webhook-structured-python",
            "description": "Structured webhook example with profile-aware replies and card hints.",
            "routes": [
                {
                    "path": "/",
                    "method": "POST",
                    "description": "Main webhook endpoint returning schema_version/status/content_parts/cards.",
                    "auth": "Optional WEBHOOK_SECRET (X-Signature)",
                }
            ],
            "schema_version": "2026-03",
        }
    )


# ---------------------------------------------------------------------------
# HMAC signature validation (same pattern as webhook-basics)
# ---------------------------------------------------------------------------


def _verify_signature(request: Request, body: bytes) -> None:
    """Raise HTTP 401 when signature validation fails.

    Validation is skipped entirely when WEBHOOK_SECRET is empty so that
    developers can iterate locally without managing secrets.
    """
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return

    provided = request.headers.get("X-Signature", "")
    if not provided:
        raise HTTPException(status_code=401, detail="Missing X-Signature header")

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Localised greeting strings
# ---------------------------------------------------------------------------

_GREETINGS: dict[str, str] = {
    "es": "Hola",
    "fr": "Bonjour",
    "pt": "Olá",
    "it": "Ciao",
}

_FALLBACK_GREETING = "Hello"


def _greeting_for_locale(locale: str) -> str:
    """Return a locale-appropriate greeting word."""
    # Use only the primary subtag (e.g. "es" from "es-MX").
    primary = locale.split("-")[0].lower() if locale else ""
    return _GREETINGS.get(primary, _FALLBACK_GREETING)


# ---------------------------------------------------------------------------
# Reply composition
# ---------------------------------------------------------------------------


def _build_reply(message_content: str, profile: dict[str, Any]) -> str:
    """Compose a personalised reply from message content and profile fields."""
    name: str = profile.get("name", "")
    locale: str = profile.get("locale", "")

    greeting = _greeting_for_locale(locale)

    if name:
        intro = f"{greeting}, {name}!"
    else:
        intro = f"{greeting}!"

    if message_content:
        return f'{intro} You said: "{message_content}"'
    return intro


# ---------------------------------------------------------------------------
# Card hints
# ---------------------------------------------------------------------------


def _build_cards(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return card hints based on context.intent."""
    intent: str = context.get("intent", "")

    if intent == "help":
        return [
            {
                "type": "suggestion",
                "text": "Need help? Here are some things I can do for you.",
                "suggestions": [
                    "Show me your features",
                    "Connect my account",
                    "Talk to support",
                ],
            }
        ]

    if intent == "product":
        return [
            {
                "type": "product_card",
                "items": [
                    {"name": "Starter", "price": "Free", "cta": "Get started"},
                    {"name": "Pro", "price": "$29/mo", "cta": "Upgrade"},
                ],
            }
        ]

    return []


def _prompt_suggestions_for_intent(intent: str) -> list[str]:
    if intent == "help":
        return [
            "Show me your features",
            "Connect my account",
            "Talk to support",
        ]
    if intent == "product":
        return [
            "Show your plans",
            "Compare Starter vs Pro",
            "How do I upgrade?",
        ]
    return [
        "What can you help me with?",
        "Show me available plans",
        "How do I get started?",
    ]


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/")
async def receive_webhook(request: Request) -> JSONResponse:
    body = await request.body()
    _verify_signature(request, body)

    try:
        data = await request.json()
    except Exception:
        data = {}

    message: dict[str, Any] = data.get("message") or {}
    profile: dict[str, Any] = data.get("profile") or {}
    context: dict[str, Any] = data.get("context") or {}

    content: str = message.get("content", "")

    reply = _build_reply(content, profile)
    cards = _build_cards(context)
    response: dict[str, Any] = {
        "schema_version": "2026-03",
        "status": "completed",
        "content_parts": [{"type": "text", "text": reply}],
        "metadata": {
            "prompt_suggestions": _prompt_suggestions_for_intent(
                context.get("intent", "")
            )
        },
    }
    if cards:
        response["cards"] = cards
    return JSONResponse(response)
