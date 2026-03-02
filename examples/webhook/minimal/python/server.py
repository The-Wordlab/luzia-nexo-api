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


class ReplyOut(BaseModel):
    reply: str


def build_reply(content: str | None) -> str:
    content = content or ""
    return f"Echo: {content}".strip()


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


@app.post("/webhook", response_model=ReplyOut)
async def receive_webhook(payload: WebhookPayload, request: Request) -> ReplyOut:
    raw_body = await request.body()
    _require_signature(request, raw_body)
    content = payload.message.content if payload.message else ""
    return ReplyOut(reply=build_reply(content))
