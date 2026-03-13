"""Nexo Webhook Contract - Pydantic models defining the CDC contract.

This is the single source of truth for:
- What Nexo sends to partner webhooks (NexoWebhookRequest)
- What partners must return (NexoWebhookResponse)
- The HMAC signature format

When Nexo changes its payload format, update these models and all examples
must pass against the new schema.

Schema version: 2026-03
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Request contract: what Nexo sends to partner webhooks
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION = "2026-03"
VALID_STATUSES = {"completed", "error"}
VALID_ACTION_STYLES = {"primary", "secondary"}


class NexoMessage(BaseModel):
    """Incoming message from the user."""

    content: str = Field(default="", description="User message text")

    model_config = {"extra": "allow"}


class NexoProfile(BaseModel):
    """User profile data (consent-scoped fields only)."""

    id: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    name: str | None = Field(default=None, description="Legacy alias for display_name")
    locale: str | None = Field(default=None, description="BCP-47 locale e.g. 'en', 'es-MX'")
    facts: list[dict[str, Any]] | None = Field(default=None)
    preferences: dict[str, Any] | None = Field(default=None)

    model_config = {"extra": "allow"}


class NexoThread(BaseModel):
    """Thread metadata."""

    id: str = Field(default="", description="Thread ID")

    model_config = {"extra": "allow"}


class NexoContext(BaseModel):
    """Conversation context."""

    intent: str | None = Field(default=None)
    app_id: str | None = Field(default=None)
    thread_id: str | None = Field(default=None)

    model_config = {"extra": "allow"}


class NexoWebhookRequest(BaseModel):
    """Canonical request that Nexo sends to partner webhooks.

    Required fields:
        message - always present (may have empty content)

    Optional fields:
        event, profile, thread, context, timestamp - Nexo may include these;
        partners must handle their absence gracefully.

    Extra fields are allowed for forward compatibility.
    """

    message: NexoMessage = Field(default_factory=NexoMessage)
    event: str | None = Field(default=None, description="e.g. 'message.created'")
    profile: NexoProfile | None = Field(default=None)
    thread: NexoThread | None = Field(default=None)
    context: NexoContext | None = Field(default=None)
    timestamp: str | None = Field(default=None, description="ISO-8601 timestamp")

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Response contract: what partners must return
# ---------------------------------------------------------------------------


class NexoContentPart(BaseModel):
    """A single content part in the response."""

    type: str = Field(description="Content type, must be 'text' for text parts")
    text: str = Field(description="Text content")

    model_config = {"extra": "allow"}

    @field_validator("type")
    @classmethod
    def type_must_be_known(cls, v: str) -> str:
        # Allow any type for forward compatibility; 'text' is the canonical value
        return v


class NexoCardField(BaseModel):
    """A key-value field on a card."""

    label: str
    value: str

    model_config = {"extra": "allow"}


class NexoCard(BaseModel):
    """A structured card in the response.

    Required: type
    Optional: title, subtitle, description, fields, badges, metadata
    Partners may include additional keys for their own card types.
    """

    type: str = Field(description="Card type identifier, e.g. 'source', 'match_result'")
    title: str | None = Field(default=None)
    subtitle: str | None = Field(default=None)
    description: str | None = Field(default=None)
    fields: list[NexoCardField] | None = Field(default=None)
    badges: list[str] | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)

    model_config = {"extra": "allow"}


class NexoAction(BaseModel):
    """An action button or link in the response.

    Required: id, label
    Optional: url, style
    """

    id: str = Field(description="Unique action identifier")
    label: str = Field(description="Button/link label text")
    url: str | None = Field(default=None, description="Target URL for link actions")
    style: str | None = Field(
        default=None,
        description="Visual style: 'primary' or 'secondary'",
    )

    model_config = {"extra": "allow"}

    @field_validator("style")
    @classmethod
    def style_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ACTION_STYLES:
            raise ValueError(f"style must be one of {VALID_ACTION_STYLES}, got {v!r}")
        return v


class NexoWebhookResponse(BaseModel):
    """Canonical response that partner webhooks must return.

    Required fields:
        schema_version - must be '2026-03'
        status         - must be 'completed' or 'error'
        content_parts  - non-empty list; at least one text part expected

    Optional fields:
        cards, actions, metadata - may be omitted or empty lists
    """

    schema_version: str = Field(description="Schema version, must be '2026-03'")
    status: str = Field(description="'completed' or 'error'")
    content_parts: list[NexoContentPart] = Field(
        description="Non-empty list of content parts"
    )
    cards: list[NexoCard] | None = Field(default=None)
    actions: list[NexoAction] | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)

    model_config = {"extra": "allow"}

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_be_current(cls, v: str) -> str:
        if v != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CURRENT_SCHEMA_VERSION!r}, got {v!r}"
            )
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_STATUSES}, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def content_parts_must_not_be_empty(self) -> "NexoWebhookResponse":
        if not self.content_parts:
            raise ValueError("content_parts must not be empty")
        return self


# ---------------------------------------------------------------------------
# SSE streaming contract
# ---------------------------------------------------------------------------


class NexoSseDeltaEvent(BaseModel):
    """SSE delta event carrying a text chunk."""

    text: str


class NexoSseDoneEvent(BaseModel):
    """SSE done event carrying the final metadata, cards, and actions."""

    schema_version: str
    status: str
    cards: list[NexoCard] | None = Field(default=None)
    actions: list[NexoAction] | None = Field(default=None)

    model_config = {"extra": "allow"}

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_be_current(cls, v: str) -> str:
        if v != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CURRENT_SCHEMA_VERSION!r}, got {v!r}"
            )
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# HMAC signature helpers
# ---------------------------------------------------------------------------

SIGNATURE_PREFIX = "sha256="


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    """Compute the HMAC-SHA256 signature Nexo attaches to every request.

    Format: sha256=HMAC(secret, "<timestamp>.<body_utf8>")

    Args:
        secret:    Shared HMAC secret (plaintext).
        timestamp: Unix timestamp string (e.g. "1700000000").
        body:      Raw request body bytes.

    Returns:
        Signature string in "sha256=<hex>" format.
    """
    signed_payload = f"{timestamp}.{body.decode('utf-8')}"
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify_signature(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Verify a Nexo HMAC signature.

    Args:
        secret:    Shared HMAC secret.
        timestamp: Value from X-Timestamp header.
        body:      Raw request body bytes.
        signature: Value from X-Signature header.

    Returns:
        True when signature is valid, False otherwise.
    """
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Canonical test request fixture
# ---------------------------------------------------------------------------

CANONICAL_REQUEST: dict = {
    "event": "message.created",
    "message": {"content": "Hello, what can you help me with?"},
    "profile": {
        "display_name": "Test User",
        "locale": "en",
    },
    "thread": {"id": "thread-test-001"},
    "context": {"intent": "help"},
    "timestamp": "2026-03-01T12:00:00Z",
}

CANONICAL_REQUEST_MINIMAL: dict = {
    "message": {"content": "Hi there"},
}
