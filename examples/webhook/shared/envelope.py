"""Response envelope builder and request parsing for Nexo partner webhooks.

Request parsing:
    Nexo sends an A2A Message-shaped payload. Use ``parse_request()`` to
    extract the user text, profile, locale, thread ID, and app metadata from
    the incoming JSON body.

    parsed = parse_request(data)
    user_text = parsed["text"]
    profile   = parsed["profile"]
    locale    = parsed["locale"]

Response building:
    envelope = build_envelope(
        cards=[news_card("Title", "https://...", snippet="...")],
        actions=[action("read_more", "Read more")],
        suggestions=["Tell me more", "Different topic"],
    )
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "2026-03"


# ---------------------------------------------------------------------------
# Request parsing (A2A Message shape with legacy fallback)
# ---------------------------------------------------------------------------


def parse_request(data: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from the incoming Nexo webhook payload.

    Supports the current A2A Message shape::

        {
          "message": {
            "parts": [{"type": "text", "text": "..."}],
            "contextId": "thread-uuid",
            "metadata": {
              "profile": {...},
              "locale": "en",
              "app": {"id": "...", "name": "..."},
              "thread": {"id": "..."},
              "history_tail": [...]
            }
          }
        }

    Falls back to the legacy flat shape for backward compatibility::

        {
          "message": {"content": "..."},
          "profile": {...},
          "thread": {"id": "..."},
          ...
        }

    Returns a dict with normalised keys:
        text, profile, locale, thread_id, app, history_tail, context, event
    """
    message = data.get("message") or {}
    metadata = message.get("metadata") or {}

    # --- user text ---
    text = _extract_text_from_parts(message)
    if not text:
        # Legacy fallback
        text = message.get("content") or ""

    # --- profile ---
    profile = metadata.get("profile") or data.get("profile") or {}

    # --- locale ---
    locale = (
        metadata.get("locale")
        or profile.get("locale")
        or profile.get("language")
        or ""
    )

    # --- thread id ---
    thread_id = (
        message.get("contextId")
        or (metadata.get("thread") or {}).get("id")
        or (data.get("thread") or {}).get("id")
        or ""
    )

    # --- app ---
    app = metadata.get("app") or data.get("app") or {}

    # --- history ---
    history_tail = metadata.get("history_tail") or data.get("history_tail") or []

    # --- context (legacy) ---
    context = data.get("context") or {}

    # --- event (legacy) ---
    event = data.get("event") or ""

    return {
        "text": text,
        "profile": profile,
        "locale": locale,
        "thread_id": thread_id,
        "app": app,
        "history_tail": history_tail,
        "context": context,
        "event": event,
    }


def _extract_text_from_parts(message: dict[str, Any]) -> str:
    """Extract text from A2A-style message.parts list."""
    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            return part.get("text", "")
    return ""


def build_envelope(
    *,
    text: str = "",
    cards: list[dict] | None = None,
    actions: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    suggestions: list[str] | None = None,
    task_id: str = "",
    status: str = "completed",
    capability: str = "",
) -> dict:
    """Build the full Nexo response envelope.

    content_parts is initialised with a text entry when text is provided.
    Streaming helpers (stream_response, stream_with_prefix) will prepend
    the accumulated stream text into content_parts before emitting the
    done event, so callers should leave content_parts empty when streaming.
    """
    content_parts: list[dict] = []
    if text:
        content_parts.append({"type": "text", "text": text})

    envelope: dict = {
        "schema_version": SCHEMA_VERSION,
        "task": {
            "id": task_id,
            "status": status,
        },
        "content_parts": content_parts,
    }

    if capability:
        envelope["capability"] = {"name": capability, "version": "1"}
    if cards:
        envelope["cards"] = cards
    if actions:
        envelope["actions"] = actions
    if artifacts:
        envelope["artifacts"] = artifacts
    if suggestions:
        envelope["suggestions"] = suggestions

    return envelope


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


def news_card(
    title: str,
    url: str,
    *,
    snippet: str = "",
    source: str = "",
    image_url: str = "",
) -> dict:
    """Build a news card for article attribution."""
    card: dict = {
        "type": "news",
        "title": title,
        "url": url,
    }
    if snippet:
        card["snippet"] = snippet
    if source:
        card["source"] = source
    if image_url:
        card["image_url"] = image_url
    return card


def product_card(
    name: str,
    price: str,
    *,
    description: str = "",
    image_url: str = "",
    dietary_labels: list[str] | None = None,
) -> dict:
    """Build a product card for food ordering or e-commerce."""
    card: dict = {
        "type": "product",
        "name": name,
        "price": price,
    }
    if description:
        card["description"] = description
    if image_url:
        card["image_url"] = image_url
    if dietary_labels:
        card["dietary_labels"] = dietary_labels
    return card


def status_card(
    title: str,
    status: str,
    *,
    details: dict | None = None,
) -> dict:
    """Build a status or tracking card."""
    card: dict = {
        "type": "status",
        "title": title,
        "status": status,
    }
    if details:
        card["details"] = details
    return card


# ---------------------------------------------------------------------------
# Action builder
# ---------------------------------------------------------------------------


def action(
    id: str,
    label: str,
    *,
    url: str = "",
    payload: dict | None = None,
) -> dict:
    """Build an action button."""
    btn: dict = {
        "id": id,
        "label": label,
    }
    if url:
        btn["url"] = url
    if payload:
        btn["payload"] = payload
    return btn


# ---------------------------------------------------------------------------
# Artifact builder
# ---------------------------------------------------------------------------


def artifact(type: str, name: str, data: object) -> dict:
    """Build an artifact (structured data attachment)."""
    return {
        "type": type,
        "name": name,
        "data": data,
    }
