"""
Tests for the news-feed RAG webhook server.

All external I/O (ChromaDB, litellm embeddings/completions, feedparser) is
mocked so the tests are fast and fully self-contained — no network calls,
no API keys, no running Ollama required.

Run with:
    pytest test_news_rag.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signature(body: bytes, secret: str, timestamp: str = "1700000000") -> tuple[str, str]:
    """Return (timestamp, sha256=<hex>) matching the server's expected format."""
    signed = f"{timestamp}.{body.decode('utf-8')}"
    digest = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return timestamp, f"sha256={digest}"


def _text_parts(data: dict) -> str:
    """Extract concatenated text from content_parts."""
    return " ".join(
        p.get("text", "")
        for p in (data.get("content_parts") or [])
        if isinstance(p, dict) and p.get("type") == "text"
    )


def _assert_envelope(data: dict) -> None:
    """Assert the canonical Nexo response envelope shape."""
    assert data["schema_version"] == "2026-03-01"
    assert data["status"] == "completed"
    assert isinstance(data.get("content_parts"), list)
    assert len(data["content_parts"]) > 0


# ---------------------------------------------------------------------------
# Sample fixture data
# ---------------------------------------------------------------------------

_SAMPLE_HITS: list[dict[str, Any]] = [
    {
        "text": "OpenAI releases GPT-5 with improved reasoning capabilities.",
        "title": "OpenAI releases GPT-5",
        "link": "https://example.com/gpt5",
        "feed": "TechCrunch",
        "published": "Fri, 07 Mar 2026 10:00:00 GMT",
        "excerpt": "OpenAI releases GPT-5 with improved reasoning...",
        "score": 0.92,
    },
    {
        "text": "Reuters: Global markets rose on positive economic data.",
        "title": "Markets rise on economic data",
        "link": "https://example.com/markets",
        "feed": "Reuters",
        "published": "Fri, 07 Mar 2026 08:30:00 GMT",
        "excerpt": "Global markets rose on positive economic data...",
        "score": 0.75,
    },
    {
        "text": "BBC: UK government announces new climate policy.",
        "title": "UK climate policy announced",
        "link": "https://example.com/climate",
        "feed": "BBC News",
        "published": "Fri, 07 Mar 2026 07:00:00 GMT",
        "excerpt": "UK government announces new climate policy...",
        "score": 0.60,
    },
]


# ---------------------------------------------------------------------------
# App fixture — returns the FastAPI app with I/O mocked
# ---------------------------------------------------------------------------


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Return the FastAPI app with:
    - WEBHOOK_SECRET unset (open access for most tests)
    - ChromaDB pointed at a temp directory
    - litellm embedding + completion calls mocked
    - feedparser mocked so no network is required
    """
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("LLM_MODEL", "ollama/llama3.2")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    import importlib
    import server

    importlib.reload(server)
    # Reset shared state
    server._collection = None
    server._chroma_client = None
    server._index_stats["num_chunks"] = 0
    server._index_stats["last_refresh"] = None

    return server.app


@pytest.fixture
def secret_app(monkeypatch, tmp_path):
    """Same as app but with WEBHOOK_SECRET=testsecret."""
    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("LLM_MODEL", "ollama/llama3.2")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    import importlib
    import server

    importlib.reload(server)
    server._collection = None
    server._chroma_client = None

    return server.app


# ---------------------------------------------------------------------------
# Unit tests: text helpers
# ---------------------------------------------------------------------------


def test_chunk_text_single_chunk():
    """Short text produces a single chunk."""
    from server import chunk_text

    chunks = chunk_text("Hello world.")
    assert chunks == ["Hello world."]


def test_chunk_text_multiple_chunks():
    """Text longer than CHUNK_SIZE_CHARS is split into multiple chunks."""
    from server import chunk_text, CHUNK_SIZE_CHARS

    long_text = "word " * (CHUNK_SIZE_CHARS // 5 + 100)
    chunks = chunk_text(long_text)
    assert len(chunks) > 1


def test_chunk_text_overlap():
    """Adjacent chunks share some content (overlap > 0)."""
    from server import chunk_text, CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS

    long_text = "A" * (CHUNK_SIZE_CHARS * 3)
    chunks = chunk_text(long_text)
    if len(chunks) >= 2:
        # The end of chunk 0 should appear in chunk 1
        tail = chunks[0][-CHUNK_OVERLAP_CHARS:]
        assert chunks[1].startswith(tail) or len(tail) == 0


def test_chunk_text_empty_input():
    """Empty string returns empty list."""
    from server import chunk_text

    assert chunk_text("") == []


def test_strip_html_removes_tags():
    """HTML tags are stripped, leaving only text."""
    from server import strip_html

    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_stable_id_is_deterministic():
    """Same input always produces the same ID."""
    from server import stable_id

    assert stable_id("test") == stable_id("test")
    assert stable_id("a") != stable_id("b")


# ---------------------------------------------------------------------------
# Unit tests: source card and action builders
# ---------------------------------------------------------------------------


def test_deduplicate_sources_keeps_highest_score():
    """When the same URL appears twice, the higher-score hit is kept."""
    from server import deduplicate_sources

    hits = [
        {"link": "https://x.com/1", "score": 0.9, "title": "A"},
        {"link": "https://x.com/1", "score": 0.5, "title": "A (dup)"},
        {"link": "https://x.com/2", "score": 0.7, "title": "B"},
    ]
    unique = deduplicate_sources(hits)
    assert len(unique) == 2
    by_link = {h["link"]: h for h in unique}
    assert by_link["https://x.com/1"]["score"] == 0.9


def test_build_source_cards_structure():
    """Source cards have the expected keys."""
    from server import build_source_cards

    cards = build_source_cards(_SAMPLE_HITS)
    assert len(cards) == 3
    for card in cards:
        assert card["type"] == "source"
        assert "title" in card
        assert "subtitle" in card
        assert "description" in card
        assert "metadata" in card
        assert "url" in card["metadata"]


def test_build_source_cards_max_three():
    """At most 3 cards are returned even with more unique hits."""
    from server import build_source_cards

    many_hits = [
        {
            "text": f"Article {i}",
            "title": f"Title {i}",
            "link": f"https://example.com/{i}",
            "feed": "Feed",
            "published": "",
            "excerpt": f"Excerpt {i}",
            "score": 0.9 - i * 0.05,
        }
        for i in range(10)
    ]
    cards = build_source_cards(many_hits)
    assert len(cards) <= 3


def test_build_read_actions_structure():
    """Actions have the expected shape for external link actions."""
    from server import build_read_actions

    actions = build_read_actions(_SAMPLE_HITS)
    assert len(actions) == 3
    for i, action in enumerate(actions):
        assert action["id"] == f"read_{i + 1}"
        assert action["label"] == "Read full article"
        assert action["url"].startswith("https://")
        assert action["style"] == "secondary"


def test_build_read_actions_skips_empty_links():
    """Hits with no link are excluded from actions."""
    from server import build_read_actions

    hits = [
        {"link": "", "score": 0.9, "title": "No link"},
        {"link": "https://example.com/a", "score": 0.8, "title": "Has link"},
    ]
    actions = build_read_actions(hits)
    assert len(actions) == 1
    assert actions[0]["url"] == "https://example.com/a"


# ---------------------------------------------------------------------------
# Unit tests: RAG prompt builder
# ---------------------------------------------------------------------------


def test_build_rag_prompt_has_system_and_user():
    """The prompt has exactly a system message and a user message."""
    from server import build_rag_prompt

    messages = build_rag_prompt(_SAMPLE_HITS[:2], "What is the latest AI news?")
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]


def test_build_rag_prompt_embeds_chunk_titles():
    """Article titles appear in the system prompt context."""
    from server import build_rag_prompt

    messages = build_rag_prompt(_SAMPLE_HITS[:1], "Any AI news?")
    system_content = messages[0]["content"]
    assert "OpenAI releases GPT-5" in system_content


def test_build_rag_prompt_user_question_preserved():
    """The user question is passed through verbatim."""
    from server import build_rag_prompt

    question = "Tell me about quantum computing breakthroughs."
    messages = build_rag_prompt(_SAMPLE_HITS[:1], question)
    assert messages[-1]["content"] == question


# ---------------------------------------------------------------------------
# Unit tests: HMAC signature verification
# ---------------------------------------------------------------------------


def test_verify_signature_passes_when_secret_unset():
    """No exception is raised when WEBHOOK_SECRET is not set."""
    import importlib
    import server

    importlib.reload(server)
    server.WEBHOOK_SECRET = ""  # ensure unset

    mock_request = MagicMock()
    mock_request.headers = {}
    server.verify_signature(mock_request, b"body")  # must not raise


def test_verify_signature_raises_on_missing_headers(monkeypatch):
    """HTTP 401 is raised when timestamp/signature headers are missing."""
    from fastapi import HTTPException
    import importlib
    import server

    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    importlib.reload(server)

    mock_request = MagicMock()
    mock_request.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        server.verify_signature(mock_request, b"body")
    assert exc_info.value.status_code == 401


def test_verify_signature_raises_on_wrong_signature(monkeypatch):
    """HTTP 401 is raised when signature is present but incorrect."""
    from fastapi import HTTPException
    import importlib
    import server

    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    importlib.reload(server)

    mock_request = MagicMock()
    mock_request.headers = {
        "x-timestamp": "1700000000",
        "x-signature": "sha256=deadbeef",
    }
    with pytest.raises(HTTPException) as exc_info:
        server.verify_signature(mock_request, b"body")
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests: webhook endpoint (mocked retrieval + LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_returns_envelope_with_results(app):
    """When RAG returns hits and the LLM responds, the envelope is well-formed."""
    import server

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=_SAMPLE_HITS)),
        patch.object(server, "ask_llm", new=AsyncMock(return_value="OpenAI just released GPT-5.")),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={"message": {"content": "What is the latest AI news?"}},
            )

    assert response.status_code == 200
    data = response.json()
    _assert_envelope(data)
    assert "OpenAI" in _text_parts(data)


@pytest.mark.asyncio
async def test_webhook_includes_source_cards(app):
    """Response cards describe the source articles."""
    import server

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=_SAMPLE_HITS)),
        patch.object(server, "ask_llm", new=AsyncMock(return_value="Here is what I found.")),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={"message": {"content": "Latest tech news?"}},
            )

    data = response.json()
    cards = data.get("cards", [])
    assert len(cards) > 0
    assert all(c["type"] == "source" for c in cards)
    # First card should be the highest-score article
    assert "OpenAI releases GPT-5" in cards[0]["title"]


@pytest.mark.asyncio
async def test_webhook_includes_read_actions(app):
    """Response actions are 'Read full article' links to source URLs."""
    import server

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=_SAMPLE_HITS)),
        patch.object(server, "ask_llm", new=AsyncMock(return_value="Answer here.")),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={"message": {"content": "Tell me the news"}},
            )

    data = response.json()
    actions = data.get("actions", [])
    assert len(actions) > 0
    assert all(a["label"] == "Read full article" for a in actions)
    assert all(a["url"].startswith("https://") for a in actions)


@pytest.mark.asyncio
async def test_webhook_empty_message_returns_prompt(app):
    """Empty message content returns a friendly prompt to ask a question."""
    import server

    with patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/", json={"message": {"content": ""}})

    assert response.status_code == 200
    data = response.json()
    _assert_envelope(data)
    assert "question" in _text_parts(data).lower()


@pytest.mark.asyncio
async def test_webhook_no_message_key_handled(app):
    """A payload with no 'message' key is handled without crashing."""
    import server

    with patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/", json={})

    assert response.status_code == 200
    _assert_envelope(response.json())


@pytest.mark.asyncio
async def test_webhook_empty_index_returns_graceful_message(app):
    """When the index is empty, response explains the index is loading."""
    import server

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=[])),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={"message": {"content": "Any news?"}},
            )

    assert response.status_code == 200
    data = response.json()
    _assert_envelope(data)
    text = _text_parts(data).lower()
    assert "index" in text or "loading" in text or "context" in text


@pytest.mark.asyncio
async def test_webhook_llm_failure_returns_graceful_fallback(app):
    """When the LLM call raises, the response still has valid structure."""
    import server

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=_SAMPLE_HITS)),
        patch.object(server, "ask_llm", new=AsyncMock(side_effect=RuntimeError("LLM down"))),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={"message": {"content": "News about AI?"}},
            )

    assert response.status_code == 200
    data = response.json()
    _assert_envelope(data)
    text = _text_parts(data).lower()
    assert "try again" in text or "couldn't" in text


@pytest.mark.asyncio
async def test_webhook_invalid_json_returns_400(app):
    """A non-JSON request body returns HTTP 400."""
    import server

    with patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=b"not json",
                headers={"Content-Type": "text/plain"},
            )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Integration tests: HMAC authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_signature_accepted(secret_app):
    """A correctly signed request is accepted (200)."""
    import server

    payload = json.dumps({"message": {"content": "hi"}}).encode()
    timestamp, sig = _make_signature(payload, "testsecret")

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=[])),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=secret_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Timestamp": timestamp,
                    "X-Signature": sig,
                },
            )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(secret_app):
    """A request with a wrong signature is rejected with 401."""
    import server

    payload = json.dumps({"message": {"content": "hi"}}).encode()

    with patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})):
        async with AsyncClient(
            transport=ASGITransport(app=secret_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Timestamp": "1700000000",
                    "X-Signature": "sha256=deadbeef",
                },
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_signature_headers_returns_401(secret_app):
    """When WEBHOOK_SECRET is set, requests without headers are rejected."""
    import server

    payload = json.dumps({"message": {"content": "hi"}}).encode()

    with patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})):
        async with AsyncClient(
            transport=ASGITransport(app=secret_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_no_secret_set_allows_any_request(app):
    """When WEBHOOK_SECRET is empty, any request is accepted without headers."""
    import server

    payload = json.dumps({"message": {"content": "hi"}}).encode()

    with (
        patch.object(server, "retrieve", new=AsyncMock(return_value=[])),
        patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Integration tests: /ingest endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_endpoint_returns_202_style_response(app):
    """POST /ingest returns immediately with status=ingest_started."""
    import server

    with patch.object(
        server, "crawl_and_index_feeds", new=AsyncMock(return_value={"num_chunks": 10, "last_refresh": "now"})
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/ingest")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ingest_started"
    assert "feeds" in data


# ---------------------------------------------------------------------------
# Integration tests: /health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok(app):
    """GET /health returns status=ok with index metadata."""
    import server

    with patch.object(server, "crawl_and_index_feeds", new=AsyncMock(return_value={})):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "chunks" in data
    assert "llm_model" in data
    assert "embedding_model" in data
    assert "vector_store" in data
    assert "backend" in data["vector_store"]
    assert "durable" in data["vector_store"]
