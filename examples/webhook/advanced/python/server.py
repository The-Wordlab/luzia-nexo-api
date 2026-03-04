#!/usr/bin/env python3
"""
Advanced connector-style webhook server.

Demonstrates four concepts beyond the intermediate tier:

1. Connector action routing
   The main webhook inspects ``context.intent`` and dispatches to a
   dedicated action handler (order_status, schedule_appointment) before
   composing the final reply.  Partners that integrate real connectors
   (e.g., a CRM, booking system, or order management platform) follow
   the same pattern: route on intent, call the connector, embed the
   result in the reply.

2. Failure / retry behavior
   The ``schedule_appointment`` action simulates transient failures.
   When a failure occurs the server returns ``success: false``,
   a ``retry_after`` delay in seconds, and a
   ``cards[0].type = "retry_suggestion"`` so the frontend
   can surface a "try again" prompt to the user.

3. Idempotency via an action log
   Every action call includes an ``action_id``.  The server keeps an
   in-memory ``action_log`` dict keyed on ``action_id``.  Repeated
   calls with the same id return the cached result immediately
   (``cached: true``) without re-executing the action.  In production
   you would store this in a database or Redis.

4. HMAC signature validation
   Same pattern as the webhook-basics and intermediate tiers.
   Validation is skipped when ``WEBHOOK_SECRET`` is unset so that
   developers can iterate locally without managing secrets.

Contract
--------

POST /
    Body:  {
               "message": {"content": "..."},
               "context": {                          # optional
                   "intent": "order_status" | "schedule_appointment",
                   "action_id": "...",               # required for idempotency
                   <action-specific fields>
               }
           }
    Reply: {
               "schema_version": "2026-03-01",
               "status": "success",
               "content_parts": [{"type": "text", "text": "<text>"}],
               "cards": [...],                        # optional
               "metadata": {"retry_after": 30}      # only on failure
           }

POST /actions/{action_type}
    Body:  {"action_id": "...", <action-specific fields>}
    Reply: {"success": true|false, "action_id": "...", <result fields>,
            "cached": true}  # only when serving a cached result

    Known action_type values:
        order_status          -> tracking data
        schedule_appointment  -> confirmation or failure with retry_after

    Unknown action_type -> HTTP 404
"""

import hashlib
import hmac
import os
import random
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="advanced-connector-webhook")

# ---------------------------------------------------------------------------
# In-memory action log (idempotency store)
# ---------------------------------------------------------------------------

# Maps action_id -> cached result dict.
action_log: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Failure simulation helper
# ---------------------------------------------------------------------------

_FAILURE_PROBABILITY = 0.4  # 40 % chance of transient failure by default
_RETRY_AFTER_SECONDS = 30


def _simulate_failure(probability: float = _FAILURE_PROBABILITY) -> bool:
    """Return True to indicate a simulated transient failure.

    In tests this function is monkeypatched to return a deterministic value.
    In production you would remove this entirely and handle real errors.
    """
    return random.random() < probability  # noqa: S311


# ---------------------------------------------------------------------------
# HMAC signature validation (same pattern as webhook-basics / intermediate)
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
# Individual action handlers
# ---------------------------------------------------------------------------


def _handle_order_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Return mock order tracking data for the given order_id."""
    order_id: str = payload.get("order_id", "UNKNOWN")
    action_id: str = payload.get("action_id", str(uuid.uuid4()))

    return {
        "success": True,
        "action_id": action_id,
        "order_id": order_id,
        "status": "in_transit",
        "tracking": {
            "carrier": "MockShip",
            "tracking_number": f"MS-{order_id[-5:] if len(order_id) >= 5 else order_id}",
            "estimated_delivery": "2025-06-20",
            "last_update": "Departed sorting facility",
        },
    }


def _handle_schedule_appointment(payload: dict[str, Any]) -> dict[str, Any]:
    """Simulate scheduling an appointment; may fail transiently."""
    action_id: str = payload.get("action_id", str(uuid.uuid4()))
    date: str = payload.get("date", "TBD")
    time_slot: str = payload.get("time", "TBD")
    service: str = payload.get("service", "general")

    if _simulate_failure():
        return {
            "success": False,
            "action_id": action_id,
            "error": "Scheduling service temporarily unavailable",
            "retry_after": _RETRY_AFTER_SECONDS,
        }

    confirmation_id = f"CONF-{uuid.uuid4().hex[:8].upper()}"
    return {
        "success": True,
        "action_id": action_id,
        "confirmation_id": confirmation_id,
        "scheduled_at": f"{date}T{time_slot}:00",
        "service": service,
    }


# ---------------------------------------------------------------------------
# Action dispatch table
# ---------------------------------------------------------------------------

_ACTION_HANDLERS = {
    "order_status": _handle_order_status,
    "schedule_appointment": _handle_schedule_appointment,
}


def _dispatch_action(
    action_type: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Dispatch to the correct action handler, return None for unknown types."""
    handler = _ACTION_HANDLERS.get(action_type)
    if handler is None:
        return None
    return handler(payload)


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------


def _check_cache(action_id: str) -> dict[str, Any] | None:
    """Return cached result for action_id if it exists, else None."""
    cached = action_log.get(action_id)
    if cached is not None:
        return {**cached, "cached": True}
    return None


def _store_result(action_id: str, result: dict[str, Any]) -> None:
    """Store action result in the action log for future idempotency checks."""
    action_log[action_id] = result


# ---------------------------------------------------------------------------
# Connector action endpoint
# ---------------------------------------------------------------------------


@app.post("/actions/{action_type}")
async def connector_action(action_type: str, request: Request) -> JSONResponse:
    """Execute (or replay) a named connector action.

    This endpoint is called directly by the main webhook handler when
    context.intent maps to a known action.  Partners can also call it
    directly to test actions in isolation.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    action_id: str = payload.get("action_id", str(uuid.uuid4()))

    # Idempotency: return cached result if this action_id was seen before
    cached = _check_cache(action_id)
    if cached is not None:
        return JSONResponse(cached)

    # Dispatch to the correct handler
    result = _dispatch_action(action_type, payload)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown action type: {action_type!r}",
        )

    # Cache the result for future replays
    _store_result(action_id, result)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Reply composition helpers
# ---------------------------------------------------------------------------


def _build_action_reply(action_result: dict[str, Any], action_type: str) -> str:
    """Build a human-readable reply from an action result."""
    if not action_result.get("success"):
        retry = action_result.get("retry_after", 30)
        return (
            f"I tried to {action_type.replace('_', ' ')} but ran into a temporary "
            f"issue. Please try again in {retry} seconds."
        )

    if action_type == "order_status":
        status = action_result.get("status", "unknown")
        order_id = action_result.get("order_id", "your order")
        tracking = action_result.get("tracking", {})
        carrier = tracking.get("carrier", "the carrier")
        eta = tracking.get("estimated_delivery", "soon")
        return (
            f"Your order {order_id} is currently {status}. "
            f"{carrier} estimates delivery by {eta}."
        )

    if action_type == "schedule_appointment":
        conf = action_result.get("confirmation_id", "N/A")
        scheduled_at = action_result.get("scheduled_at", "the requested time")
        return (
            f"Your appointment has been scheduled for {scheduled_at}. "
            f"Confirmation ID: {conf}."
        )

    return "Action completed successfully."


def _build_action_cards(
    action_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build cards based on the action result."""
    if not action_result.get("success"):
        return [
            {
                "type": "retry_suggestion",
                "message": action_result.get("error", "Temporary error"),
                "retry_after": action_result.get("retry_after", _RETRY_AFTER_SECONDS),
            }
        ]

    return [
        {
            "type": "action_result",
            "success": True,
            "data": {
                k: v
                for k, v in action_result.items()
                if k not in {"success", "action_id", "cached"}
            },
        }
    ]


# ---------------------------------------------------------------------------
# Main webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/")
async def receive_webhook(request: Request) -> JSONResponse:
    """Main webhook endpoint.

    Inspects context.intent to decide whether to trigger a connector
    action.  When an action is triggered the content and cards are
    derived from the action result.  A failed action surfaces retry
    guidance to the caller.
    """
    body = await request.body()
    _verify_signature(request, body)

    try:
        data = await request.json()
    except Exception:
        data = {}

    message: dict[str, Any] = data.get("message") or {}
    context: dict[str, Any] = data.get("context") or {}

    intent: str = context.get("intent", "")
    action_id: str = context.get("action_id", str(uuid.uuid4()))

    # Route to connector action if intent maps to a known action
    if intent in _ACTION_HANDLERS:
        # Merge context fields into the action payload
        action_payload = {**context, "action_id": action_id}

        # Check idempotency cache first
        cached = _check_cache(action_id)
        if cached is not None:
            action_result = cached
        else:
            action_result = _dispatch_action(intent, action_payload)
            if action_result is not None:
                _store_result(action_id, action_result)

        reply = _build_action_reply(action_result, intent)
        cards = _build_action_cards(action_result)
        response_body: dict[str, Any] = {
            "schema_version": "2026-03-01",
            "status": "success",
            "content_parts": [{"type": "text", "text": reply}],
            "cards": cards,
        }
        if not action_result.get("success"):
            response_body["metadata"] = {
                "retry_after": action_result.get("retry_after", _RETRY_AFTER_SECONDS)
            }
        return JSONResponse(response_body)

    # Plain message - no connector action needed
    content: str = message.get("content", "")
    reply_text = f'Received: "{content}"' if content else "Hello! How can I help you?"
    return JSONResponse(
        {
            "schema_version": "2026-03-01",
            "status": "success",
            "content_parts": [{"type": "text", "text": reply_text}],
        }
    )
