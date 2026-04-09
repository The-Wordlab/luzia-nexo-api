"""SSE streaming helpers for Nexo partner webhooks.

Partners stream LLM output as plain `data:` lines. Nexo normalizes
these into content_delta events for downstream consumers.

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
    """Stream LLM tokens as data: lines, then emit done with envelope.

    Accumulates full text and adds it to envelope.content_parts automatically.
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

    yield f"event: done\ndata: {json.dumps(envelope)}\n\n"


async def stream_with_prefix(
    prefix: str,
    llm_stream: AsyncIterator[str],
    envelope: dict,
) -> AsyncIterator[str]:
    """Like stream_response but emits a prefix before LLM streaming."""
    if prefix:
        yield f"data: {prefix}\n\n"

    full_text = prefix
    async for chunk in llm_stream:
        if chunk:
            full_text += chunk
            yield f"data: {chunk}\n\n"

    content_parts = envelope.get("content_parts", [])
    if full_text:
        content_parts.insert(0, {"type": "text", "text": full_text})
    envelope["content_parts"] = content_parts

    yield f"event: done\ndata: {json.dumps(envelope)}\n\n"
