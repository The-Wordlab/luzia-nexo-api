"""CDC: Response contract tests.

Verifies that each webhook example returns responses that validate against
the NexoWebhookResponse schema. Uses httpx.AsyncClient with each example's
FastAPI app to make real HTTP calls.

These tests catch response drift — if an example starts returning wrong
status values, missing content_parts, or malformed cards/actions, these
tests will fail.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from nexo_webhook_contract import (
    CANONICAL_REQUEST,
    CANONICAL_REQUEST_MINIMAL,
    NexoWebhookResponse,
    NexoCard,
    NexoAction,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples"))
from test_support.fake_vector_store import FakeVectorStoreRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_response(data: dict) -> NexoWebhookResponse:
    """Parse and validate a response dict against the contract.

    Raises ValidationError on contract violation.
    """
    return NexoWebhookResponse(**data)


def _assert_valid_response(data: dict) -> NexoWebhookResponse:
    """Assert response validates and return the parsed model."""
    try:
        return _validate_response(data)
    except ValidationError as exc:
        pytest.fail(f"Response violates contract:\n{exc}\n\nResponse was:\n{data}")


# ---------------------------------------------------------------------------
# Response contract unit tests (schema-level)
# ---------------------------------------------------------------------------


def test_minimal_valid_response_validates() -> None:
    """A minimal valid response satisfies the contract."""
    resp = NexoWebhookResponse(
        schema_version="2026-03-01",
        status="success",
        content_parts=[{"type": "text", "text": "Hello"}],
    )
    assert resp.schema_version == "2026-03-01"
    assert resp.status == "success"
    assert len(resp.content_parts) == 1


def test_completed_status_is_valid() -> None:
    """Status 'completed' (used by RAG examples) is valid."""
    resp = NexoWebhookResponse(
        schema_version="2026-03-01",
        status="completed",
        content_parts=[{"type": "text", "text": "Done"}],
    )
    assert resp.status == "completed"


def test_error_status_is_valid() -> None:
    """Status 'error' is valid for error responses."""
    resp = NexoWebhookResponse(
        schema_version="2026-03-01",
        status="error",
        content_parts=[{"type": "text", "text": "Something went wrong"}],
    )
    assert resp.status == "error"


def test_wrong_schema_version_fails() -> None:
    """A response with wrong schema_version violates the contract."""
    with pytest.raises(ValidationError, match="schema_version"):
        NexoWebhookResponse(
            schema_version="2025-01-01",
            status="success",
            content_parts=[{"type": "text", "text": "Hi"}],
        )


def test_wrong_status_fails() -> None:
    """A response with an unknown status value violates the contract."""
    with pytest.raises(ValidationError, match="status"):
        NexoWebhookResponse(
            schema_version="2026-03-01",
            status="ok",  # not a valid status
            content_parts=[{"type": "text", "text": "Hi"}],
        )


def test_empty_content_parts_fails() -> None:
    """A response with empty content_parts violates the contract."""
    with pytest.raises(ValidationError, match="content_parts"):
        NexoWebhookResponse(
            schema_version="2026-03-01",
            status="success",
            content_parts=[],
        )


def test_missing_schema_version_fails() -> None:
    """A response without schema_version violates the contract."""
    with pytest.raises(ValidationError):
        NexoWebhookResponse(
            status="success",
            content_parts=[{"type": "text", "text": "Hi"}],
        )


def test_missing_content_parts_fails() -> None:
    """A response without content_parts violates the contract."""
    with pytest.raises(ValidationError):
        NexoWebhookResponse(
            schema_version="2026-03-01",
            status="success",
        )


# ---------------------------------------------------------------------------
# Card shape tests
# ---------------------------------------------------------------------------


def test_card_requires_type() -> None:
    """A card without a type violates the contract."""
    with pytest.raises(ValidationError):
        NexoCard()  # no type


def test_card_allows_all_optional_fields() -> None:
    """A card with all optional fields is valid."""
    card = NexoCard(
        type="source",
        title="Article Title",
        subtitle="BBC News",
        description="Short excerpt...",
        fields=[{"label": "Date", "value": "2026-03-01"}],
        badges=["News", "Live"],
        metadata={"capability_state": "live", "url": "https://example.com"},
    )
    assert card.type == "source"
    assert len(card.fields) == 1
    assert card.fields[0].label == "Date"


def test_card_allows_extra_fields() -> None:
    """Cards may contain extra fields for partner-specific use cases."""
    card = NexoCard(
        type="custom_partner_card",
        title="Custom Card",
        partner_specific_field="value",
        another_field=42,
    )
    assert card.type == "custom_partner_card"


# ---------------------------------------------------------------------------
# Action shape tests
# ---------------------------------------------------------------------------


def test_action_requires_id_and_label() -> None:
    """An action without id or label violates the contract."""
    with pytest.raises(ValidationError):
        NexoAction(id="act-1")  # missing label
    with pytest.raises(ValidationError):
        NexoAction(label="Click me")  # missing id


def test_action_valid_styles() -> None:
    """Actions may have 'primary' or 'secondary' style."""
    a1 = NexoAction(id="a1", label="Primary", style="primary")
    a2 = NexoAction(id="a2", label="Secondary", style="secondary")
    assert a1.style == "primary"
    assert a2.style == "secondary"


def test_action_invalid_style_fails() -> None:
    """An action with an unknown style violates the contract."""
    with pytest.raises(ValidationError, match="style"):
        NexoAction(id="a1", label="Bad", style="link")


def test_action_without_style_is_valid() -> None:
    """Actions without style are valid (optional field)."""
    action = NexoAction(id="read_1", label="Read full article", url="https://example.com")
    assert action.style is None


def test_action_without_url_is_valid() -> None:
    """Actions without URL are valid (e.g., in-app actions)."""
    action = NexoAction(id="retry", label="Try again", style="primary")
    assert action.url is None


# ---------------------------------------------------------------------------
# Minimal example - response compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_example_response_validates(make_client):
    """Minimal example returns a contract-compliant response."""
    # Add minimal example to sys.path
    minimal_path = Path(__file__).parent.parent.parent / "examples/webhook/minimal/python"
    sys.path.insert(0, str(minimal_path))
    try:
        import importlib
        import server as minimal_server
        importlib.reload(minimal_server)

        async with make_client(minimal_server.app) as client:
            resp = await client.post("/webhook", json=CANONICAL_REQUEST)

        assert resp.status_code == 200
        _assert_valid_response(resp.json())
    finally:
        sys.path.remove(str(minimal_path))
        if "server" in sys.modules:
            del sys.modules["server"]


@pytest.mark.asyncio
async def test_minimal_example_minimal_request_validates(make_client):
    """Minimal example handles a minimal-payload request correctly."""
    minimal_path = Path(__file__).parent.parent.parent / "examples/webhook/minimal/python"
    sys.path.insert(0, str(minimal_path))
    try:
        import importlib
        import server as minimal_server
        importlib.reload(minimal_server)

        async with make_client(minimal_server.app) as client:
            resp = await client.post("/webhook", json=CANONICAL_REQUEST_MINIMAL)

        assert resp.status_code == 200
        _assert_valid_response(resp.json())
    finally:
        sys.path.remove(str(minimal_path))
        if "server" in sys.modules:
            del sys.modules["server"]


# ---------------------------------------------------------------------------
# Structured example - response compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_example_plain_response_validates(make_client):
    """Structured example returns a contract-compliant plain text response."""
    structured_path = Path(__file__).parent.parent.parent / "examples/webhook/structured/python"
    sys.path.insert(0, str(structured_path))
    try:
        import importlib
        # structured server is named differently; load it
        spec = __import__.__self__  # noqa: won't work; use importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "structured_server",
            structured_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        async with make_client(mod.app) as client:
            resp = await client.post("/", json=CANONICAL_REQUEST)

        assert resp.status_code == 200
        _assert_valid_response(resp.json())
    finally:
        sys.path.remove(str(structured_path))
        for key in list(sys.modules.keys()):
            if "structured_server" in key:
                del sys.modules[key]


@pytest.mark.asyncio
async def test_structured_example_help_intent_has_cards(make_client):
    """Structured example includes cards when context.intent='help'."""
    structured_path = Path(__file__).parent.parent.parent / "examples/webhook/structured/python"
    sys.path.insert(0, str(structured_path))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "structured_server2",
            structured_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = {
            "message": {"content": "I need help"},
            "context": {"intent": "help"},
        }
        async with make_client(mod.app) as client:
            resp = await client.post("/", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        validated = _assert_valid_response(data)
        # Structured example returns cards for help intent
        assert validated.cards is not None
        assert len(validated.cards) > 0
        for card in validated.cards:
            assert card.type  # type must not be empty
    finally:
        sys.path.remove(str(structured_path))
        for key in list(sys.modules.keys()):
            if "structured_server2" in key:
                del sys.modules[key]


# ---------------------------------------------------------------------------
# Advanced example - response compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_advanced_example_plain_response_validates(make_client):
    """Advanced example plain message returns a contract-compliant response."""
    advanced_path = Path(__file__).parent.parent.parent / "examples/webhook/advanced/python"
    sys.path.insert(0, str(advanced_path))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "advanced_server",
            advanced_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = {"message": {"content": "Hello"}}
        async with make_client(mod.app) as client:
            resp = await client.post("/", json=payload)

        assert resp.status_code == 200
        _assert_valid_response(resp.json())
    finally:
        sys.path.remove(str(advanced_path))
        for key in list(sys.modules.keys()):
            if "advanced_server" in key:
                del sys.modules[key]


@pytest.mark.asyncio
async def test_advanced_example_action_response_has_cards(make_client):
    """Advanced example with order_status intent returns cards."""
    import unittest.mock
    advanced_path = Path(__file__).parent.parent.parent / "examples/webhook/advanced/python"
    sys.path.insert(0, str(advanced_path))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "advanced_server2",
            advanced_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.action_log.clear()

        payload = {
            "message": {"content": "Where is my order?"},
            "context": {
                "intent": "order_status",
                "action_id": "contract-test-001",
                "order_id": "ORD-12345",
            },
        }
        with unittest.mock.patch.object(mod, "_simulate_failure", return_value=False):
            async with make_client(mod.app) as client:
                resp = await client.post("/", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        validated = _assert_valid_response(data)
        assert validated.cards is not None
        assert len(validated.cards) > 0
    finally:
        sys.path.remove(str(advanced_path))
        for key in list(sys.modules.keys()):
            if "advanced_server2" in key:
                del sys.modules[key]


# ---------------------------------------------------------------------------
# News-RAG example - response compliance
# (skipped when litellm/feedparser are not installed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_news_rag_example_empty_index_validates(make_client, monkeypatch, tmp_path):
    """News-RAG example with empty index returns contract-compliant response."""
    pytest.importorskip("litellm", reason="litellm not installed; skipping news-rag tests")
    pytest.importorskip("feedparser", reason="feedparser not installed; skipping news-rag tests")

    news_rag_path = Path(__file__).parent.parent.parent / "examples/webhook/news-rag/python"
    sys.path.insert(0, str(news_rag_path))
    try:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
        monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")

        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "news_rag_server",
            news_rag_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Reset shared state
        fake_store = FakeVectorStoreRegistry()
        mod._collection = fake_store.get()
        mod.get_collection = lambda: fake_store.get()

        from unittest.mock import AsyncMock
        with (
            patch.object(mod, "retrieve", new=AsyncMock(return_value=[])),
            patch.object(mod, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
        ):
            async with make_client(mod.app) as client:
                resp = await client.post("/", json={"message": {"content": "Any news?"}})

        assert resp.status_code == 200
        _assert_valid_response(resp.json())
    finally:
        sys.path.remove(str(news_rag_path))
        for key in list(sys.modules.keys()):
            if "news_rag_server" in key:
                del sys.modules[key]


@pytest.mark.asyncio
async def test_news_rag_example_with_results_validates(make_client, monkeypatch, tmp_path):
    """News-RAG example with LLM results returns contract-compliant response with cards and actions."""
    pytest.importorskip("litellm", reason="litellm not installed; skipping news-rag tests")
    pytest.importorskip("feedparser", reason="feedparser not installed; skipping news-rag tests")

    news_rag_path = Path(__file__).parent.parent.parent / "examples/webhook/news-rag/python"
    sys.path.insert(0, str(news_rag_path))
    try:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
        monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "news_rag_server2",
            news_rag_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fake_store = FakeVectorStoreRegistry()
        mod._collection = fake_store.get()
        mod.get_collection = lambda: fake_store.get()

        sample_hits = [
            {
                "text": "AI advances in 2026.",
                "title": "AI in 2026",
                "link": "https://example.com/ai",
                "feed": "TechNews",
                "published": "2026-03-01",
                "excerpt": "AI advances...",
                "score": 0.9,
            }
        ]
        from unittest.mock import AsyncMock
        with (
            patch.object(mod, "retrieve", new=AsyncMock(return_value=sample_hits)),
            patch.object(mod, "ask_llm", new=AsyncMock(return_value="AI has advanced greatly.")),
            patch.object(mod, "crawl_and_index_feeds", new=AsyncMock(return_value={})),
        ):
            async with make_client(mod.app) as client:
                resp = await client.post(
                    "/",
                    json={"message": {"content": "What is happening in AI?"}},
                )

        assert resp.status_code == 200
        data = resp.json()
        validated = _assert_valid_response(data)
        assert validated.cards is not None
        assert validated.actions is not None
    finally:
        sys.path.remove(str(news_rag_path))
        for key in list(sys.modules.keys()):
            if "news_rag_server2" in key:
                del sys.modules[key]


# ---------------------------------------------------------------------------
# Travel-RAG example - response compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_travel_rag_example_empty_index_validates(make_client, monkeypatch, tmp_path):
    """Travel-RAG example with empty index returns contract-compliant response."""
    travel_rag_path = Path(__file__).parent.parent.parent / "examples/webhook/travel-rag/python"
    sys.path.insert(0, str(travel_rag_path))
    try:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
        monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")

        import importlib.util
        # Load ingest module first (dependency of server)
        ingest_spec = importlib.util.spec_from_file_location(
            "travel_ingest",
            travel_rag_path / "ingest.py",
        )
        ingest_mod = importlib.util.module_from_spec(ingest_spec)
        sys.modules["ingest"] = ingest_mod
        ingest_spec.loader.exec_module(ingest_mod)
        fake_store = FakeVectorStoreRegistry()
        ingest_mod._destinations_collection = fake_store.get("destinations")
        ingest_mod._articles_collection = fake_store.get("articles")

        spec = importlib.util.spec_from_file_location(
            "travel_rag_server",
            travel_rag_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        from unittest.mock import MagicMock
        # Mock search functions to return empty results
        with (
            patch.object(mod, "search_destinations", return_value=[]),
            patch.object(mod, "search_articles", return_value=[]),
        ):
            async with make_client(mod.app) as client:
                resp = await client.post("/", json={"message": {"content": "Where should I go?"}})

        assert resp.status_code == 200
        _assert_valid_response(resp.json())
    finally:
        sys.path.remove(str(travel_rag_path))
        for key in list(sys.modules.keys()):
            if "travel" in key.lower() or key == "ingest":
                del sys.modules[key]


@pytest.mark.asyncio
async def test_travel_rag_example_with_destinations_validates(make_client, monkeypatch, tmp_path):
    """Travel-RAG example with destination results returns contract-compliant response with cards."""
    travel_rag_path = Path(__file__).parent.parent.parent / "examples/webhook/travel-rag/python"
    sys.path.insert(0, str(travel_rag_path))
    try:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
        monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")

        import importlib.util
        ingest_spec = importlib.util.spec_from_file_location(
            "travel_ingest2",
            travel_rag_path / "ingest.py",
        )
        ingest_mod = importlib.util.module_from_spec(ingest_spec)
        sys.modules["ingest"] = ingest_mod
        ingest_spec.loader.exec_module(ingest_mod)
        fake_store = FakeVectorStoreRegistry()
        ingest_mod._destinations_collection = fake_store.get("destinations")
        ingest_mod._articles_collection = fake_store.get("articles")

        spec = importlib.util.spec_from_file_location(
            "travel_rag_server2",
            travel_rag_path / "server.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        sample_destinations = [
            {
                "text": "Destination: Paris, France (Western Europe)\nDescription: City of Light...",
                "city": "Paris",
                "country": "France",
                "region": "Western Europe",
                "best_time": "April to June",
                "budget_range": "$150-$300/day",
                "language": "French",
                "currency": "Euro (EUR)",
                "highlights": "Eiffel Tower, Louvre, Notre-Dame",
                "tags": "romantic, culture, history",
                "distance": 0.2,
            }
        ]

        with (
            patch.object(mod, "search_destinations", return_value=sample_destinations),
            patch.object(mod, "search_articles", return_value=[]),
            patch.object(mod, "call_llm", return_value="Paris is a wonderful destination."),
        ):
            async with make_client(mod.app) as client:
                resp = await client.post(
                    "/",
                    json={"message": {"content": "Tell me about Paris"}},
                )

        assert resp.status_code == 200
        data = resp.json()
        validated = _assert_valid_response(data)
        assert validated.cards is not None
        assert len(validated.cards) > 0
        # Destination card should have type and title
        assert validated.cards[0].type == "destination"
        assert "Paris" in validated.cards[0].title
    finally:
        sys.path.remove(str(travel_rag_path))
        for key in list(sys.modules.keys()):
            if "travel" in key.lower() or key == "ingest":
                del sys.modules[key]
