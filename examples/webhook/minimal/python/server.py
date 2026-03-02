"""Minimal webhook receiver example.

Purpose: smallest possible webhook contract implementation.
"""

from __future__ import annotations

from fastapi import FastAPI
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


app = FastAPI(title="nexo-examples minimal webhook")


@app.post("/webhook", response_model=ReplyOut)
async def receive_webhook(payload: WebhookPayload) -> ReplyOut:
    content = payload.message.content if payload.message else ""
    return ReplyOut(reply=build_reply(content))
