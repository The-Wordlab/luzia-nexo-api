"""Webhook contract schemas - mirrors Nexo runtime contract.

Nexo sends an A2A Message-shaped payload::

    {
      "message": {
        "messageId": "uuid",
        "contextId": "thread-uuid",
        "role": "user",
        "parts": [{"type": "text", "text": "..."}],
        "metadata": {
          "app": {"id": "uuid", "name": "..."},
          "thread": {"id": "uuid"},
          "profile": {"display_name": "Alice", "locale": "en", ...},
          "locale": "en",
          "history_tail": [...]
        }
      }
    }

The legacy flat shape is also accepted for backward compatibility.
"""

from typing import Any
from pydantic import BaseModel, Field


class WebhookMessagePart(BaseModel):
    """A single part in the A2A message.parts array."""
    type: str = Field(default="text")
    text: str = Field(default="")


class WebhookMessage(BaseModel):
    """Incoming message from Nexo (A2A shape with legacy fallback)."""
    role: str = Field(default="user", description="Message role: user/assistant/system")
    # Legacy field
    content: str = Field(default="", description="Message text content (legacy)")
    # A2A fields
    parts: list[WebhookMessagePart] | None = Field(default=None, description="A2A message parts")
    messageId: str | None = Field(default=None, description="A2A message ID")
    contextId: str | None = Field(default=None, description="A2A context/thread ID")
    metadata: dict[str, Any] | None = Field(default=None, description="A2A message metadata")

    def get_text(self) -> str:
        """Extract user text from parts (A2A) or content (legacy)."""
        if self.parts:
            for part in self.parts:
                if part.type == "text" and part.text:
                    return part.text
        return self.content or ""


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
    """Incoming webhook request from Nexo.

    Accepts both A2A Message shape (message.parts, message.metadata.profile)
    and legacy flat shape (message.content, top-level profile).
    """
    event: str = Field(default="", description="Event type: message_created")
    app: dict[str, Any] = Field(default_factory=dict, description="App metadata")
    thread: dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    message: WebhookMessage = Field(default_factory=WebhookMessage)
    # Legacy top-level fields (A2A puts these in message.metadata)
    profile: WebhookProfile | None = Field(default=None, description="User profile (legacy)")
    context: WebhookContext | None = Field(default=None, description="Conversation context")
    history_tail: list[WebhookHistoryEntry] | None = Field(default=None, description="Recent messages (legacy)")

    def get_text(self) -> str:
        """Extract user text from A2A parts or legacy content."""
        return self.message.get_text()

    def get_profile(self) -> WebhookProfile | None:
        """Get profile from A2A metadata or legacy top-level field."""
        metadata = self.message.metadata or {}
        meta_profile = metadata.get("profile")
        if meta_profile and isinstance(meta_profile, dict):
            return WebhookProfile(**meta_profile)
        return self.profile

    def get_locale(self) -> str | None:
        """Get locale from A2A metadata, profile, or legacy field."""
        metadata = self.message.metadata or {}
        locale = metadata.get("locale")
        if locale:
            return locale
        profile = self.get_profile()
        if profile and profile.locale:
            return profile.locale
        return None

    def get_history(self) -> list[WebhookHistoryEntry]:
        """Get history from A2A metadata or legacy top-level field."""
        metadata = self.message.metadata or {}
        meta_history = metadata.get("history_tail")
        if meta_history and isinstance(meta_history, list):
            return [WebhookHistoryEntry(**h) for h in meta_history if isinstance(h, dict)]
        return self.history_tail or []

    def get_thread_id(self) -> str:
        """Get thread ID from A2A contextId, metadata, or legacy field."""
        if self.message.contextId:
            return self.message.contextId
        metadata = self.message.metadata or {}
        meta_thread = metadata.get("thread") or {}
        if isinstance(meta_thread, dict) and meta_thread.get("id"):
            return meta_thread["id"]
        return self.thread.get("id", "")


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
