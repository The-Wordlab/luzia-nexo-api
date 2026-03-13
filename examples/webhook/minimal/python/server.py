"""Minimal webhook receiver example.

Purpose: smallest possible webhook contract implementation.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import FastAPI
from fastapi import HTTPException, Request
from pydantic import BaseModel


class MessageIn(BaseModel):
    content: str | None = ""


class WebhookPayload(BaseModel):
    event: str | None = None
    message: MessageIn | None = None
    profile: dict | None = None


class ContentPartOut(BaseModel):
    type: str
    text: str


class WebhookResponseOut(BaseModel):
    schema_version: str
    status: str
    content_parts: list[ContentPartOut]
    metadata: dict | None = None


def _extract_profile_context(
    profile: dict | None,
) -> tuple[str | None, str | None, str | None]:
    data = profile or {}
    display_name = data.get("display_name") or data.get("name")
    locale = data.get("locale") or data.get("language")
    dietary = data.get("dietary_preferences")
    return display_name, locale, dietary


def build_reply(
    content: str | None,
    *,
    display_name: str | None = None,
    locale: str | None = None,
    dietary_preferences: str | None = None,
) -> str:
    content = content or ""
    if display_name:
        base = f"{display_name}, you said: {content}".strip()
    else:
        base = f"Echo: {content}".strip()

    # Example of defensive profile usage - include optional hints only when present.
    hints: list[str] = []
    if locale:
        hints.append(f"locale={locale}")
    if dietary_preferences:
        hints.append(f"dietary={dietary_preferences}")
    if hints:
        return f"{base} ({', '.join(hints)})"
    return base


def verify_signature(secret: str, raw_body: bytes, timestamp: str, signature: str) -> bool:
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
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return

    timestamp = request.headers.get("x-timestamp", "")
    signature = request.headers.get("x-signature", "")
    if not verify_signature(secret, raw_body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


app = FastAPI(title="nexo-examples minimal webhook")


def _default_prompt_suggestions() -> list[str]:
    return [
        "Help me plan dinner",
        "Track my order status",
        "Show options under $20",
    ]


@app.get("/")
async def root() -> dict:
    """Service discovery endpoint for local/manual testing."""
    return {
        "service": "webhook-minimal-python",
        "description": "Minimal Nexo webhook example with optional HMAC verification.",
        "routes": [
            {
                "path": "/webhook",
                "method": "POST",
                "description": "Receive Nexo webhook payload and return response envelope.",
                "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
            }
        ],
        "schema_version": "2026-03",
    }


@app.post("/webhook", response_model=WebhookResponseOut)
async def receive_webhook(payload: WebhookPayload, request: Request) -> WebhookResponseOut:
    raw_body = await request.body()
    _require_signature(request, raw_body)
    # Parse optional profile fields defensively and ignore unknown additions.
    display_name, locale, dietary = _extract_profile_context(payload.profile)
    content = payload.message.content if payload.message else ""
    return WebhookResponseOut(
        schema_version="2026-03",
        status="completed",
        content_parts=[
            ContentPartOut(
                type="text",
                text=build_reply(
                    content,
                    display_name=display_name,
                    locale=locale,
                    dietary_preferences=dietary,
                ),
            )
        ],
        metadata={"prompt_suggestions": _default_prompt_suggestions()},
    )
