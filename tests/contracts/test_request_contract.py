"""CDC: Request contract tests.

Verifies that canonical Nexo request payloads validate correctly against
the NexoWebhookRequest schema. This is the "consumer" side of the contract:
Nexo is the consumer that sends these payloads.

These tests catch schema drift in the request definition — if the Nexo team
changes what they send, these tests will fail and highlight the contract break.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexo_webhook_contract import (
    CANONICAL_REQUEST,
    CANONICAL_REQUEST_MINIMAL,
    NexoWebhookRequest,
    NexoMessage,
    NexoProfile,
    NexoThread,
    NexoContext,
)


# ---------------------------------------------------------------------------
# Canonical payloads validate correctly
# ---------------------------------------------------------------------------


def test_canonical_request_is_valid() -> None:
    """The full canonical request payload validates without errors."""
    req = NexoWebhookRequest(**CANONICAL_REQUEST)
    assert req.message.content == "Hello, what can you help me with?"
    assert req.event == "message.created"
    assert req.profile is not None
    assert req.profile.display_name == "Test User"
    assert req.profile.locale == "en"
    assert req.thread is not None
    assert req.thread.id == "thread-test-001"
    assert req.context is not None
    assert req.context.intent == "help"


def test_minimal_request_is_valid() -> None:
    """The minimal request (message only) validates without errors."""
    req = NexoWebhookRequest(**CANONICAL_REQUEST_MINIMAL)
    assert req.message.content == "Hi there"
    assert req.event is None
    assert req.profile is None
    assert req.thread is None


# ---------------------------------------------------------------------------
# Required and optional fields
# ---------------------------------------------------------------------------


def test_request_without_message_uses_default() -> None:
    """A request with no message field uses an empty-content default."""
    req = NexoWebhookRequest()
    assert req.message.content == ""


def test_request_message_content_may_be_empty() -> None:
    """Empty string content is valid (user submitted empty message)."""
    req = NexoWebhookRequest(message={"content": ""})
    assert req.message.content == ""


def test_request_profile_is_optional() -> None:
    """Profile may be absent — partners must handle None gracefully."""
    req = NexoWebhookRequest(message={"content": "hello"})
    assert req.profile is None


def test_request_thread_is_optional() -> None:
    """Thread may be absent."""
    req = NexoWebhookRequest(message={"content": "hello"})
    assert req.thread is None


def test_request_context_is_optional() -> None:
    """Context may be absent."""
    req = NexoWebhookRequest(message={"content": "hello"})
    assert req.context is None


def test_request_event_is_optional() -> None:
    """Event type may be absent in early Nexo versions."""
    req = NexoWebhookRequest(message={"content": "hello"})
    assert req.event is None


# ---------------------------------------------------------------------------
# Forward-compatibility: extra fields are allowed
# ---------------------------------------------------------------------------


def test_request_allows_extra_fields() -> None:
    """Unknown fields in the request are tolerated (forward-compat)."""
    req = NexoWebhookRequest(
        message={"content": "hello"},
        future_field="ignored",
        another_new_field={"nested": True},
    )
    assert req.message.content == "hello"


def test_profile_allows_extra_fields() -> None:
    """Unknown profile fields are tolerated (partners must not break on new fields)."""
    req = NexoWebhookRequest(
        message={"content": "hello"},
        profile={
            "display_name": "Ana",
            "locale": "pt",
            "unknown_future_field": "some_value",
            "dietary_preferences": "vegan",
        },
    )
    assert req.profile is not None
    assert req.profile.display_name == "Ana"


# ---------------------------------------------------------------------------
# Profile field semantics
# ---------------------------------------------------------------------------


def test_profile_display_name_takes_precedence_over_name() -> None:
    """When both display_name and name are present, both are accessible."""
    profile = NexoProfile(display_name="Alice", name="alice_legacy")
    assert profile.display_name == "Alice"
    assert profile.name == "alice_legacy"


def test_profile_locale_format() -> None:
    """Locale values include BCP-47 subtags."""
    profile = NexoProfile(locale="es-MX")
    assert profile.locale == "es-MX"


def test_profile_facts_is_list_of_dicts() -> None:
    """Facts field contains a list of arbitrary dicts."""
    profile = NexoProfile(
        facts=[{"key": "age", "value": "30"}, {"key": "city", "value": "London"}]
    )
    assert len(profile.facts) == 2
    assert profile.facts[0]["key"] == "age"


# ---------------------------------------------------------------------------
# Message field semantics
# ---------------------------------------------------------------------------


def test_message_with_only_content() -> None:
    """Message containing only content field is valid."""
    msg = NexoMessage(content="What is the weather?")
    assert msg.content == "What is the weather?"


def test_message_allows_extra_fields() -> None:
    """Extra message fields (e.g., role, attachments) are tolerated."""
    msg = NexoMessage(content="Hello", role="user", attachments=[])
    assert msg.content == "Hello"
