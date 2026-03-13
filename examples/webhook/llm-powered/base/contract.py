"""Webhook contract schemas - mirrors Nexo runtime contract."""

from typing import Any
from pydantic import BaseModel, Field


class WebhookMessage(BaseModel):
    """Incoming message from Nexo."""
    role: str = Field(default="user", description="Message role: user/assistant/system")
    content: str = Field(default="", description="Message text content")


class WebhookProfile(BaseModel):
    """User profile data passed from Nexo (consent-scoped)."""
    id: str | None = Field(default=None, description="Profile ID")
    # Nexo sends `display_name`; keep `name` for backward compatibility.
    display_name: str | None = Field(default=None, description="User's display name")
    name: str | None = Field(default=None, description="User's name (legacy key)")
    locale: str | None = Field(default=None, description="User locale (e.g., 'en', 'es-MX')")
    facts: list[dict[str, Any]] | None = Field(
        default=None,
        description="User facts/memory entries",
    )
    preferences: dict[str, Any] | None = Field(default=None, description="User preferences")


class WebhookContext(BaseModel):
    """Conversation context from Nexo."""
    intent: str | None = Field(default=None, description="Detected intent")
    app_id: str | None = Field(default=None, description="App ID")
    thread_id: str | None = Field(default=None, description="Thread ID")


class WebhookHistoryEntry(BaseModel):
    """Previous message in conversation."""
    role: str
    content: str


class WebhookRequest(BaseModel):
    """Incoming webhook request from Nexo."""
    event: str = Field(description="Event type: message_created")
    app: dict[str, Any] = Field(default_factory=dict, description="App metadata")
    thread: dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    message: WebhookMessage = Field(default_factory=WebhookMessage)
    profile: WebhookProfile | None = Field(default=None, description="User profile")
    context: WebhookContext | None = Field(default=None, description="Conversation context")
    history_tail: list[WebhookHistoryEntry] | None = Field(default=None, description="Recent messages")


class ContentPart(BaseModel):
    """Text content part."""
    type: str = Field(default="text")
    text: str


class CardSuggestion(BaseModel):
    """Suggestion chip."""
    text: str


class Card(BaseModel):
    """Response card."""
    type: str = Field(description="Card type: suggestion, product_card, etc.")
    text: str | None = Field(default=None, description="Card title/text")
    suggestions: list[CardSuggestion] | None = Field(default=None, description="Suggestion chips")
    items: list[dict[str, Any]] | None = Field(default=None, description="Product/items")


class WebhookResponse(BaseModel):
    """Response to send back to Nexo."""
    schema_version: str = Field(default="2026-03")
    status: str = Field(default="completed", description="completed or error")
    content_parts: list[ContentPart] = Field(default_factory=list)
    cards: list[Card] | None = Field(default=None)
    actions: list[dict[str, Any]] | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)


def build_text_response(text: str) -> WebhookResponse:
    """Helper to build a simple text response."""
    return WebhookResponse(
        content_parts=[ContentPart(type="text", text=text)]
    )


def build_response_with_suggestions(text: str, suggestions: list[str]) -> WebhookResponse:
    """Helper to build a text response with suggestion chips."""
    return WebhookResponse(
        content_parts=[ContentPart(type="text", text=text)],
        cards=[Card(
            type="suggestion",
            text="Here are some things I can help with:",
            suggestions=[CardSuggestion(text=s) for s in suggestions]
        )]
    )
