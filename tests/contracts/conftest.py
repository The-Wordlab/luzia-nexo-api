"""Shared fixtures for CDC contract tests.

Provides:
- canonical_request: full Nexo request payload
- canonical_request_minimal: minimal valid Nexo request
- make_signed_headers: factory for X-Timestamp / X-Signature headers
- client_for: httpx.AsyncClient factory for any FastAPI app
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Make the contract importable by tests in this package
CONTRACT_DIR = Path(__file__).parent
ROOT_DIR = CONTRACT_DIR.parent.parent

from nexo_webhook_contract import (
    CANONICAL_REQUEST,
    CANONICAL_REQUEST_MINIMAL,
    compute_signature,
)


# ---------------------------------------------------------------------------
# Request fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def canonical_request() -> dict:
    """Full canonical Nexo request payload."""
    return dict(CANONICAL_REQUEST)


@pytest.fixture
def canonical_request_minimal() -> dict:
    """Minimal valid Nexo request (only message)."""
    return dict(CANONICAL_REQUEST_MINIMAL)


# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def make_signed_headers():
    """Factory: return HTTP headers with a valid HMAC signature.

    Usage::

        headers = make_signed_headers("my-secret", body_bytes)
        # -> {"X-Timestamp": "...", "X-Signature": "sha256=..."}
    """

    def _factory(secret: str, body: bytes, timestamp: str = "1700000000") -> dict[str, str]:
        sig = compute_signature(secret, timestamp, body)
        return {
            "X-Timestamp": timestamp,
            "X-Signature": sig,
            "Content-Type": "application/json",
        }

    return _factory


# ---------------------------------------------------------------------------
# HTTP client factory
# ---------------------------------------------------------------------------


@pytest.fixture
def make_client():
    """Factory: create an httpx.AsyncClient for a FastAPI app (async context manager).

    Usage::

        async with make_client(app) as client:
            resp = await client.post("/", json=payload)
    """

    def _factory(app) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _factory
