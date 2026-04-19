"""CDC: SSE streaming contract tests.

Validates both sides of the SSE story:
  - Nexo outbound vocabulary still uses named events like stream_start and
    content_delta
  - partner-side shared helpers emit the inbound contract Nexo expects:
    plain ``data:`` lines for chunks and ``event: done`` at the end

These tests exercise the shared partner helpers directly and verify that
they emit the correct inbound structure.
"""

from __future__ import annotations

import json

import pytest

from nexo_webhook_contract import (
    NexoSseStreamStartEvent,
    NexoSseContentDeltaEvent,
    NexoSseDeltaEvent,
    NexoSseDoneEvent,
    SSE_EVENT_STREAM_START,
    SSE_EVENT_CONTENT_DELTA,
    SSE_EVENT_DONE,
    SSE_EVENT_ENRICHMENT,
    SSE_EVENT_ERROR,
    parse_sse_events,
)


# ---------------------------------------------------------------------------
# Event type constant tests
# ---------------------------------------------------------------------------


def test_sse_event_type_constants() -> None:
    """Canonical SSE event type strings are defined."""
    assert SSE_EVENT_STREAM_START == "stream_start"
    assert SSE_EVENT_CONTENT_DELTA == "content_delta"
    assert SSE_EVENT_DONE == "done"
    assert SSE_EVENT_ENRICHMENT == "enrichment"
    assert SSE_EVENT_ERROR == "error"


# ---------------------------------------------------------------------------
# NexoSseStreamStartEvent model tests
# ---------------------------------------------------------------------------


def test_stream_start_event_can_be_empty() -> None:
    """stream_start event is valid with no fields (metadata is optional)."""
    event = NexoSseStreamStartEvent()
    assert event is not None


def test_stream_start_event_allows_extra_fields() -> None:
    """stream_start event accepts optional metadata fields."""
    event = NexoSseStreamStartEvent(response_id="r123", thread_id="t456")
    assert event.model_extra["response_id"] == "r123"
    assert event.model_extra["thread_id"] == "t456"


# ---------------------------------------------------------------------------
# NexoSseContentDeltaEvent model tests
# ---------------------------------------------------------------------------


def test_content_delta_event_requires_text() -> None:
    """content_delta event requires a text field."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        NexoSseContentDeltaEvent()  # type: ignore[call-arg]


def test_content_delta_event_valid() -> None:
    """content_delta event accepts a text chunk."""
    event = NexoSseContentDeltaEvent(text="Hello")
    assert event.text == "Hello"


def test_delta_alias_is_content_delta() -> None:
    """NexoSseDeltaEvent is an alias for NexoSseContentDeltaEvent for backwards compat."""
    assert NexoSseDeltaEvent is NexoSseContentDeltaEvent


# ---------------------------------------------------------------------------
# NexoSseDoneEvent model tests
# ---------------------------------------------------------------------------


def test_done_event_valid_minimal() -> None:
    """done event is valid with schema_version and status only."""
    event = NexoSseDoneEvent(schema_version="2026-03", status="completed")
    assert event.schema_version == "2026-03"
    assert event.status == "completed"
    assert event.text is None


def test_done_event_accepts_text_field() -> None:
    """done event accepts optional accumulated text."""
    event = NexoSseDoneEvent(
        schema_version="2026-03",
        status="completed",
        text="Full response text here.",
    )
    assert event.text == "Full response text here."


def test_done_event_text_field_is_optional() -> None:
    """done event text field is optional for backwards compatibility."""
    event = NexoSseDoneEvent(schema_version="2026-03", status="completed")
    assert event.text is None


def test_done_event_wrong_schema_version_fails() -> None:
    """done event rejects unknown schema_version."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="schema_version"):
        NexoSseDoneEvent(schema_version="2025-01", status="completed")


def test_done_event_wrong_status_fails() -> None:
    """done event rejects unknown status value."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="status"):
        NexoSseDoneEvent(schema_version="2026-03", status="ok")


def test_done_event_accepts_cards_and_actions() -> None:
    """done event accepts cards and actions (same shape as JSON response)."""
    event = NexoSseDoneEvent(
        schema_version="2026-03",
        status="completed",
        text="Done.",
        cards=[{"type": "source", "title": "Test"}],
        actions=[{"id": "a1", "label": "Click"}],
    )
    assert len(event.cards) == 1
    assert event.cards[0].type == "source"
    assert len(event.actions) == 1


# ---------------------------------------------------------------------------
# parse_sse_events helper tests
# ---------------------------------------------------------------------------


def test_parse_sse_events_named_events() -> None:
    """parse_sse_events parses named event blocks correctly."""
    raw = (
        "event: stream_start\n"
        "data: {}\n"
        "\n"
        "event: content_delta\n"
        'data: {"text": "Hello "}\n'
        "\n"
        "event: content_delta\n"
        'data: {"text": "world"}\n'
        "\n"
        "event: done\n"
        'data: {"schema_version": "2026-03", "status": "completed", "text": "Hello world"}\n'
        "\n"
    )
    events = parse_sse_events(raw)
    assert len(events) == 4
    assert events[0] == ("stream_start", {})
    assert events[1] == ("content_delta", {"text": "Hello "})
    assert events[2] == ("content_delta", {"text": "world"})
    assert events[3][0] == "done"
    assert events[3][1]["text"] == "Hello world"


def test_parse_sse_events_bare_data_lines() -> None:
    """parse_sse_events treats bare data lines (no event:) as type 'data'."""
    raw = "data: Hello\n\ndata: World\n\n"
    events = parse_sse_events(raw)
    assert len(events) == 2
    assert events[0] == ("data", "Hello")
    assert events[1] == ("data", "World")


def test_parse_sse_events_empty_stream() -> None:
    """parse_sse_events returns empty list for empty input."""
    assert parse_sse_events("") == []


# ---------------------------------------------------------------------------
# Streaming helper integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_response_emits_plain_data_chunks_first() -> None:
    """stream_response emits bare data chunks first, not Nexo-outbound events."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples/webhook/shared"))
    try:
        import streaming as streaming_mod

        async def _chunks():
            yield "Hello "
            yield "world"

        envelope = {"schema_version": "2026-03", "status": "completed"}
        raw = "".join([chunk async for chunk in streaming_mod.stream_response(_chunks(), envelope)])

        events = parse_sse_events(raw)
        assert events, "Expected at least one event"
        assert events[0] == ("data", "Hello")
        assert events[1] == ("data", "world")
    finally:
        sys.path.remove(
            str(Path(__file__).parent.parent.parent / "examples/webhook/shared")
        )
        if "streaming" in sys.modules:
            del sys.modules["streaming"]


@pytest.mark.asyncio
async def test_stream_response_does_not_emit_named_delta_events() -> None:
    """stream_response emits bare data lines, not content_delta/delta events."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples/webhook/shared"))
    try:
        import streaming as streaming_mod

        async def _chunks():
            yield "chunk1"
            yield "chunk2"

        envelope = {"schema_version": "2026-03", "status": "completed"}
        raw = "".join([chunk async for chunk in streaming_mod.stream_response(_chunks(), envelope)])

        events = parse_sse_events(raw)
        data_events = [(et, d) for et, d in events if et == "data"]
        delta_events = [(et, d) for et, d in events if et == "content_delta"]
        legacy_delta_events = [(et, d) for et, d in events if et == "delta"]

        assert data_events == [("data", "chunk1"), ("data", "chunk2")]
        assert len(delta_events) == 0, f"Unexpected content_delta events: {delta_events}"
        assert len(legacy_delta_events) == 0, f"Unexpected legacy delta events: {legacy_delta_events}"
    finally:
        sys.path.remove(
            str(Path(__file__).parent.parent.parent / "examples/webhook/shared")
        )
        if "streaming" in sys.modules:
            del sys.modules["streaming"]


@pytest.mark.asyncio
async def test_stream_response_done_event_includes_text() -> None:
    """stream_response done event includes the accumulated text field."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples/webhook/shared"))
    try:
        import streaming as streaming_mod

        async def _chunks():
            yield "Hello "
            yield "world"

        envelope = {"schema_version": "2026-03", "status": "completed"}
        raw = "".join([chunk async for chunk in streaming_mod.stream_response(_chunks(), envelope)])

        events = parse_sse_events(raw)
        done_events = [(et, d) for et, d in events if et == SSE_EVENT_DONE]

        assert len(done_events) == 1, f"Expected 1 done event, got {len(done_events)}"
        done_data = done_events[0][1]
        assert "text" in done_data, f"done event missing 'text' field: {done_data}"
        assert done_data["text"] == "Hello world", (
            f"done event text mismatch: expected 'Hello world', got {done_data['text']!r}"
        )
    finally:
        sys.path.remove(
            str(Path(__file__).parent.parent.parent / "examples/webhook/shared")
        )
        if "streaming" in sys.modules:
            del sys.modules["streaming"]


@pytest.mark.asyncio
async def test_stream_with_prefix_emits_plain_data_chunks() -> None:
    """stream_with_prefix emits bare data lines for prefix and chunks."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples/webhook/shared"))
    try:
        import streaming as streaming_mod

        async def _chunks():
            yield "rest"

        envelope = {"schema_version": "2026-03", "status": "completed"}
        raw = "".join([
            chunk async for chunk in streaming_mod.stream_with_prefix(
                "prefix ", _chunks(), envelope
            )
        ])

        events = parse_sse_events(raw)
        data_events = [(et, d) for et, d in events if et == "data"]
        delta_events = [(et, d) for et, d in events if et == "content_delta"]
        legacy_events = [(et, d) for et, d in events if et == "delta"]

        assert len(legacy_events) == 0, f"Legacy 'delta' events found: {legacy_events}"
        assert len(delta_events) == 0, f"Unexpected content_delta events: {delta_events}"
        assert data_events == [("data", "prefix"), ("data", "rest")]
    finally:
        sys.path.remove(
            str(Path(__file__).parent.parent.parent / "examples/webhook/shared")
        )
        if "streaming" in sys.modules:
            del sys.modules["streaming"]
