from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel


class MessageIn(BaseModel):
    content: str | None = ""


class WebhookPayload(BaseModel):
    event: str | None = None
    message: MessageIn | None = None
    context: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None


class ReplyOut(BaseModel):
    reply: str
    content_json: dict[str, Any] | None = None
    retry_after: int | None = None


def _shared_secret() -> str:
    return os.getenv("EXAMPLES_SHARED_API_SECRET", "")


def _is_authorized(x_app_secret: str | None, authorization: str | None) -> bool:
    expected = _shared_secret()
    if not expected:
        return False
    if x_app_secret and x_app_secret == expected:
        return True
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        return token == expected
    return False


def _require_auth(x_app_secret: str | None, authorization: str | None) -> None:
    if not _is_authorized(x_app_secret, authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="nexo-examples-py")


def _info_payload() -> dict[str, Any]:
    return {
        "service": "nexo-examples-py",
        "runtime": "python",
        "description": (
            "Lucia Nexo hosted Python examples. Use these endpoints as a reference, "
            "then clone and extend the examples in GitHub for your integration."
        ),
        "docs_url": "https://the-wordlab.github.io/luzia-nexo-api/",
        "auth": {
            "shared_secret_env": "EXAMPLES_SHARED_API_SECRET",
            "headers": ["X-App-Secret", "Authorization: Bearer <secret>"],
        },
        "endpoints": [
            {"path": "/health", "method": "GET", "description": "Service health", "auth_required": False},
            {"path": "/info", "method": "GET", "description": "Service endpoint catalog", "auth_required": False},
            {"path": "/webhook/minimal", "method": "POST", "description": "Minimal echo webhook", "auth_required": True},
            {"path": "/webhook/structured", "method": "POST", "description": "Structured webhook with profile handling", "auth_required": True},
            {"path": "/webhook/advanced", "method": "POST", "description": "Advanced webhook with intent routing", "auth_required": True},
            {"path": "/partner/proactive/preview", "method": "POST", "description": "Proactive message contract preview", "auth_required": True},
        ],
    }


def _render_info_html(info: dict[str, Any]) -> str:
    endpoint_rows = "".join(
        (
            "<tr>"
            f"<td><code>{e['method']}</code></td>"
            f"<td><code>{e['path']}</code></td>"
            f"<td>{e['description']}</td>"
            f"<td>{'yes' if e['auth_required'] else 'no'}</td>"
            "</tr>"
        )
        for e in info["endpoints"]
    )
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Lucia Nexo - {info['service']}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; }}
      h1 {{ margin-bottom: 4px; }}
      p {{ margin-top: 0; color: #4b5563; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
      th, td {{ border: 1px solid #e5e7eb; padding: 10px; text-align: left; font-size: 14px; }}
      th {{ background: #f9fafb; }}
      code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 4px; }}
      .hint {{ margin-top: 16px; font-size: 13px; color: #6b7280; }}
    </style>
  </head>
  <body>
    <h1>Lucia Nexo - {info['service']}</h1>
    <p>{info['description']}</p>
    <p><a href="{info['docs_url']}" target="_blank" rel="noopener noreferrer">Integration guide, quickstart, and runnable example code</a></p>
    <table>
      <thead><tr><th>Method</th><th>Path</th><th>Description</th><th>Auth</th></tr></thead>
      <tbody>{endpoint_rows}</tbody>
    </table>
    <p class="hint">For JSON output, request <code>/info?format=json</code> or send <code>Accept: application/json</code>.</p>
  </body>
</html>"""


def _wants_json(request: Request, format: str | None) -> bool:
    if format == "json":
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


@app.get("/")
async def root(request: Request, format: str | None = None):
    info = _info_payload()
    if _wants_json(request, format):
        return JSONResponse(info)
    return HTMLResponse(_render_info_html(info))


@app.get("/info")
async def info(request: Request, format: str | None = None):
    info_data = _info_payload()
    if _wants_json(request, format):
        return JSONResponse(info_data)
    return HTMLResponse(_render_info_html(info_data))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "nexo-examples-py",
        "runtime": "python",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.post("/webhook/minimal", response_model=ReplyOut)
async def webhook_minimal(
    payload: WebhookPayload,
    x_app_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ReplyOut:
    _require_auth(x_app_secret, authorization)
    content = payload.message.content if payload.message else ""
    profile = payload.profile or {}
    name = (
        profile.get("display_name")
        or profile.get("name")
        if isinstance(profile, dict)
        else None
    )
    locale = (
        profile.get("locale") or profile.get("language")
        if isinstance(profile, dict)
        else None
    )
    dietary = (
        profile.get("dietary_preferences") if isinstance(profile, dict) else None
    )
    text = f"{name}, you said: {content}" if name else f"Echo: {content}".strip()
    hints: list[str] = []
    if isinstance(locale, str) and locale:
        hints.append(f"locale={locale}")
    if isinstance(dietary, str) and dietary:
        hints.append(f"dietary={dietary}")
    if hints:
        text = f"{text} ({', '.join(hints)})"
    return ReplyOut(reply=text)


@app.post("/webhook/structured", response_model=ReplyOut)
async def webhook_structured(
    payload: WebhookPayload,
    x_app_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ReplyOut:
    _require_auth(x_app_secret, authorization)
    profile = payload.profile or {}
    name = profile.get("name") if isinstance(profile.get("name"), str) else "there"
    content = payload.message.content if payload.message else ""
    reply = f"Hello, {name}. Echo: {content.upper() if content else '(empty)'}"
    return ReplyOut(reply=reply)


@app.post("/webhook/advanced", response_model=ReplyOut)
async def webhook_advanced(
    payload: WebhookPayload,
    x_app_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ReplyOut:
    _require_auth(x_app_secret, authorization)
    context = payload.context or {}
    intent = context.get("intent") if isinstance(context.get("intent"), str) else ""

    if intent == "schedule_appointment" and bool(context.get("force_fail")):
        return ReplyOut(
            reply="Scheduling is temporarily unavailable. Please retry soon.",
            content_json={
                "type": "retry_suggestion",
                "retry_after": 30,
            },
            retry_after=30,
        )

    if intent == "order_status":
        order_id = context.get("order_id") if isinstance(context.get("order_id"), str) else "UNKNOWN"
        return ReplyOut(
            reply=f"Order {order_id} is in transit.",
            content_json={
                "type": "action_result",
                "status": "in_transit",
                "order_id": order_id,
            },
        )

    content = payload.message.content if payload.message else ""
    return ReplyOut(reply=f'Received: "{content}"' if content else "Hello! How can I help?")


@app.post("/partner/proactive/preview")
async def proactive_preview(
    x_app_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_auth(x_app_secret, authorization)
    return {
        "message": {
            "role": "assistant",
            "content": "Your order is arriving in 15 minutes.",
        },
        "headers": {
            "X-App-Id": "<app-id>",
            "X-App-Secret": "<shared-secret>",
        },
    }
