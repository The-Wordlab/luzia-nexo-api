"""Response envelope builder for Nexo partner webhooks.

Usage:
    envelope = build_envelope(
        cards=[news_card("Title", "https://...", snippet="...")],
        actions=[action("read_more", "Read more")],
        suggestions=["Tell me more", "Different topic"],
    )
"""

from __future__ import annotations

SCHEMA_VERSION = "2026-03"


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
