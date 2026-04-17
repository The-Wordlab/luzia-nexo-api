"""SSE streaming helpers for Nexo partner webhooks.

Canonical SSE event vocabulary:
  stream_start   - first event signalling the stream has begun (metadata optional)
  content_delta  - text chunk events emitted for each LLM token
  done           - final event with schema_version, status, text, cards, actions

Reserved event types (not yet emitted here):
  enrichment     - cards/actions streaming mid-response
  error          - standalone error event

Usage:
    return StreamingResponse(
        stream_response(llm_chunks, envelope),
        media_type="text/event-stream",
    )
"""

from __future__ import annotations

import json
from typing import AsyncIterator


async def stream_response(
    llm_stream: AsyncIterator[str],
    envelope: dict,
) -> AsyncIterator[str]:
    """Stream LLM tokens as SSE content_delta events, then emit done with envelope.

    Emits:
      1. stream_start  - empty metadata object (signals stream beginning)
      2. content_delta - one event per non-empty LLM chunk
      3. done          - final envelope including accumulated ``text`` field

    Accumulates full text and adds it to both the ``text`` field on the done
    event and to envelope.content_parts automatically.
    """
    # Signal that the stream is beginning
    yield f"event: stream_start\ndata: {{}}\n\n"

    full_text = ""
    async for chunk in llm_stream:
        if chunk:
            full_text += chunk
            yield f"event: content_delta\ndata: {json.dumps({'text': chunk})}\n\n"

    # Add accumulated text to envelope
    content_parts = envelope.get("content_parts", [])
    if full_text:
        content_parts.insert(0, {"type": "text", "text": full_text})
    envelope["content_parts"] = content_parts

    # Include full accumulated text in done event
    envelope["text"] = full_text

    yield f"event: done\ndata: {json.dumps(envelope)}\n\n"


async def stream_with_prefix(
    prefix: str,
    llm_stream: AsyncIterator[str],
    envelope: dict,
) -> AsyncIterator[str]:
    """Like stream_response but emits a prefix chunk before LLM streaming.

    Emits:
      1. stream_start  - empty metadata object
      2. content_delta - for prefix (if non-empty), then for each LLM chunk
      3. done          - final envelope including accumulated ``text`` field
    """
    # Signal that the stream is beginning
    yield f"event: stream_start\ndata: {{}}\n\n"

    full_text = prefix
    if prefix:
        yield f"event: content_delta\ndata: {json.dumps({'text': prefix})}\n\n"

    async for chunk in llm_stream:
        if chunk:
            full_text += chunk
            yield f"event: content_delta\ndata: {json.dumps({'text': chunk})}\n\n"

    content_parts = envelope.get("content_parts", [])
    if full_text:
        content_parts.insert(0, {"type": "text", "text": full_text})
    envelope["content_parts"] = content_parts

    # Include full accumulated text in done event
    envelope["text"] = full_text

    yield f"event: done\ndata: {json.dumps(envelope)}\n\n"
