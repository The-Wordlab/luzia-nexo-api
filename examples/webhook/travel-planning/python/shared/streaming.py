"""SSE streaming helpers for Nexo partner webhooks.

Partners stream LLM output as plain ``data:`` lines. Nexo normalizes
these into content_delta events for downstream consumers.

Inbound partner SSE contract (what your webhook should emit):
  plain data: <chunk>  - one per LLM token/chunk; no event: line needed
  event: done          - final event with schema_version, task.status, text, cards, actions
  event: error         - explicit partner-side failure (optional)

Do NOT emit ``event: content_delta`` or ``event: stream_start``.
Those are Nexo-outbound event types (Nexo -> frontend) and are not part
of the inbound partner contract. Nexo's parser accepts them for compatibility
but the preferred partner format uses plain data: lines.

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
    """Stream LLM tokens as plain data: lines, then emit done with envelope.

    Emits:
      1. data: <chunk>  - one per non-empty LLM chunk (no event: line)
      2. event: done    - final envelope including accumulated ``text`` field

    Accumulates full text and adds it to both the ``text`` field on the done
    event and to envelope.content_parts automatically.
    """
    full_text = ""
    async for chunk in llm_stream:
        if chunk:
            full_text += chunk
            yield f"data: {chunk}\n\n"

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
      1. data: <prefix>  - if non-empty
      2. data: <chunk>   - one per non-empty LLM chunk
      3. event: done     - final envelope including accumulated ``text`` field
    """
    full_text = prefix
    if prefix:
        yield f"data: {prefix}\n\n"

    async for chunk in llm_stream:
        if chunk:
            full_text += chunk
            yield f"data: {chunk}\n\n"

    content_parts = envelope.get("content_parts", [])
    if full_text:
        content_parts.insert(0, {"type": "text", "text": full_text})
    envelope["content_parts"] = content_parts

    # Include full accumulated text in done event
    envelope["text"] = full_text

    yield f"event: done\ndata: {json.dumps(envelope)}\n\n"
