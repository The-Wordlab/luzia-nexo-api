"""Shared utilities for Nexo partner webhook examples.

Modules:
    sessions  - DB-backed session store (asyncpg, keyed by thread_id)
    streaming - SSE streaming helpers (stream_response, stream_with_prefix)
    envelope  - Response envelope builder with typed card/action helpers

Note: SessionStore is imported lazily to avoid a hard dependency on asyncpg
in environments that only use the envelope/streaming helpers. Import it
directly from the sessions module when needed:

    from shared.sessions import SessionStore
"""

from .envelope import (
    action,
    artifact,
    build_envelope,
    news_card,
    product_card,
    status_card,
)
from .streaming import stream_response, stream_with_prefix

__all__ = [
    # envelope
    "build_envelope",
    "news_card",
    "product_card",
    "status_card",
    "action",
    "artifact",
    # sessions (import from shared.sessions directly)
    "SessionStore",
    # streaming
    "stream_response",
    "stream_with_prefix",
]


def __getattr__(name: str) -> object:
    if name == "SessionStore":
        from .sessions import SessionStore  # noqa: PLC0415

        return SessionStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
