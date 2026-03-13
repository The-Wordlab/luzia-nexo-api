"""CDC: Parameterized compliance test for all webhook examples.

Each webhook example is loaded and exercised against a canonical request.
The test verifies:
1. The example accepts the canonical request (HTTP 200)
2. The response validates against NexoWebhookResponse
3. No required fields are missing
4. Extra fields in the response are tolerated (extensibility)

Adding a new example? Add an entry to WEBHOOK_EXAMPLES below.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from nexo_webhook_contract import (
    CANONICAL_REQUEST,
    CANONICAL_REQUEST_MINIMAL,
    NexoWebhookResponse,
)

EXAMPLES_ROOT = Path(__file__).parent.parent.parent / "examples/webhook"
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples"))
from test_support.fake_vector_store import FakeVectorStoreRegistry

# ---------------------------------------------------------------------------
# Example registry
#
# Each entry describes one webhook example:
#   id       - unique pytest ID
#   path     - path to the Python directory containing server.py
#   endpoint - the webhook endpoint path (POST)
#   module   - name to use when loading the module (avoids sys.modules collisions)
#   setup    - optional callable(mod, monkeypatch, tmp_path) to mock I/O
# ---------------------------------------------------------------------------


def _setup_news_rag(mod: Any, monkeypatch: Any, tmp_path: Path) -> None:
    """Patch pgvector-backed retrieval and LLM for the news-RAG example."""
    del tmp_path
    fake_store = FakeVectorStoreRegistry()
    mod._collection = fake_store.get()
    mod.get_collection = lambda: fake_store.get()
    monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
    monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")
    # Patch retrieve and crawl at the module level so they're intercepted
    # regardless of when app startup fires
    sample_hits = [
        {
            "text": "Test article content.",
            "title": "Test Article",
            "link": "https://example.com/test",
            "feed": "TestFeed",
            "published": "2026-03-01",
            "excerpt": "Test excerpt.",
            "score": 0.9,
        }
    ]
    mod.retrieve = AsyncMock(return_value=sample_hits)
    mod.ask_llm = AsyncMock(return_value="Here is a test answer.")
    mod.crawl_and_index_feeds = AsyncMock(return_value={})


def _setup_sports_rag(mod: Any, monkeypatch: Any, tmp_path: Path) -> None:
    """Patch pgvector-backed retrieval and LLM for the sports-RAG example."""
    del tmp_path
    import ingest as sports_ingest
    fake_store = FakeVectorStoreRegistry()
    sports_ingest._collection_matches = fake_store.get("matches")
    sports_ingest._collection_articles = fake_store.get("articles")
    sports_ingest._collection_standings = fake_store.get("standings")
    monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
    monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")
    # Patch LLM call so no network is required
    mod.call_llm = lambda system, user: "Test sports answer."
    # Patch search functions to return seed data
    mod.search_matches = lambda q, n_results=3: []
    mod.search_articles = lambda q, n_results=3: []
    mod.search_standings = lambda q, n_results=1: []


def _setup_travel_rag(mod: Any, monkeypatch: Any, tmp_path: Path) -> None:
    """Patch pgvector-backed retrieval and LLM for the travel-RAG example."""
    del tmp_path
    fake_store = FakeVectorStoreRegistry()
    mod._destinations_collection = fake_store.get("destinations")
    mod._articles_collection = fake_store.get("articles")
    monkeypatch.setenv("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
    monkeypatch.setenv("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")
    # Patch LLM call so no network is required
    mod.call_llm = lambda system, user: "Test travel answer."
    # Patch search functions to return empty results
    mod.search_destinations = lambda q, n_results=4: []
    mod.search_articles = lambda q, n_results=3: []


WEBHOOK_EXAMPLES = [
    {
        "id": "minimal",
        "path": EXAMPLES_ROOT / "minimal/python",
        "endpoint": "/webhook",
        "module": "example_minimal",
        "setup": None,
    },
    {
        "id": "structured",
        "path": EXAMPLES_ROOT / "structured/python",
        "endpoint": "/",
        "module": "example_structured",
        "setup": None,
    },
    {
        "id": "advanced",
        "path": EXAMPLES_ROOT / "advanced/python",
        "endpoint": "/",
        "module": "example_advanced",
        "setup": None,
    },
    {
        "id": "news-rag",
        "path": EXAMPLES_ROOT / "news-rag/python",
        "endpoint": "/",
        "module": "example_news_rag",
        "setup": _setup_news_rag,
        "requires": ["litellm", "feedparser"],
    },
    {
        "id": "sports-rag",
        "path": EXAMPLES_ROOT / "sports-rag/python",
        "endpoint": "/",
        "module": "example_sports_rag",
        "setup": _setup_sports_rag,
        "requires": ["litellm"],
    },
    {
        "id": "travel-rag",
        "path": EXAMPLES_ROOT / "travel-rag/python",
        "endpoint": "/",
        "module": "example_travel_rag",
        "setup": _setup_travel_rag,
        "requires": ["litellm", "feedparser"],
    },
]


# ---------------------------------------------------------------------------
# Helper: load a webhook example's FastAPI app
# ---------------------------------------------------------------------------


def _skip_if_missing_deps(example: dict) -> None:
    """Skip the test if any required package is not importable."""
    for dep in example.get("requires", []):
        pytest.importorskip(dep, reason=f"{dep} not installed; skipping {example['id']} tests")


def _load_example_app(example: dict, monkeypatch: Any, tmp_path: Path) -> Any:
    """Load a webhook example module and return its FastAPI app."""
    _skip_if_missing_deps(example)

    path = example["path"]
    module_name = example["module"]

    sys.path.insert(0, str(path))
    try:
        spec = importlib.util.spec_from_file_location(module_name, path / "server.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

        setup_fn = example.get("setup")
        if setup_fn is not None:
            setup_fn(mod, monkeypatch, tmp_path)

        return mod.app
    finally:
        sys.path.remove(str(path))


def _cleanup_example(example: dict) -> None:
    """Remove example module from sys.modules."""
    module_name = example["module"]
    sys.modules.pop(module_name, None)
    # Clean up any ingest modules loaded transitively
    for key in list(sys.modules.keys()):
        if key.startswith(module_name):
            del sys.modules[key]
    # Clean up shared module names that different examples may load
    # (e.g. each RAG example has its own ingest.py)
    sys.modules.pop("ingest", None)


# ---------------------------------------------------------------------------
# Parameterized compliance tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_accepts_canonical_request(example, monkeypatch, tmp_path):
    """Each example returns HTTP 200 for the canonical Nexo request."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=CANONICAL_REQUEST)
        assert resp.status_code == 200, (
            f"Example '{example['id']}' returned {resp.status_code} for canonical request.\n"
            f"Body: {resp.text}"
        )
    finally:
        _cleanup_example(example)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_response_validates_against_contract(example, monkeypatch, tmp_path):
    """Each example's response validates against NexoWebhookResponse."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=CANONICAL_REQUEST)

        assert resp.status_code == 200
        data = resp.json()
        try:
            validated = NexoWebhookResponse(**data)
        except ValidationError as exc:
            pytest.fail(
                f"Example '{example['id']}' response violates contract:\n{exc}\n"
                f"Response: {json.dumps(data, indent=2)}"
            )
    finally:
        _cleanup_example(example)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_accepts_minimal_request(example, monkeypatch, tmp_path):
    """Each example returns HTTP 200 for the minimal Nexo request (no profile/thread/context)."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=CANONICAL_REQUEST_MINIMAL)

        assert resp.status_code == 200, (
            f"Example '{example['id']}' returned {resp.status_code} for minimal request.\n"
            f"Body: {resp.text}"
        )
        data = resp.json()
        try:
            NexoWebhookResponse(**data)
        except ValidationError as exc:
            pytest.fail(
                f"Example '{example['id']}' minimal response violates contract:\n{exc}"
            )
    finally:
        _cleanup_example(example)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_response_has_required_fields(example, monkeypatch, tmp_path):
    """Each example's response includes all required contract fields."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=CANONICAL_REQUEST)

        assert resp.status_code == 200
        data = resp.json()

        # Check each required field explicitly for clearer failure messages
        assert "schema_version" in data, (
            f"Example '{example['id']}': missing required field 'schema_version'"
        )
        assert "status" in data, (
            f"Example '{example['id']}': missing required field 'status'"
        )
        assert "content_parts" in data, (
            f"Example '{example['id']}': missing required field 'content_parts'"
        )
        assert isinstance(data["content_parts"], list), (
            f"Example '{example['id']}': 'content_parts' must be a list"
        )
        assert len(data["content_parts"]) > 0, (
            f"Example '{example['id']}': 'content_parts' must not be empty"
        )
        assert data["schema_version"] == "2026-03", (
            f"Example '{example['id']}': schema_version must be '2026-03', "
            f"got {data['schema_version']!r}"
        )
        assert data["status"] in {"completed", "error"}, (
            f"Example '{example['id']}': status must be 'completed' or 'error', "
            f"got {data['status']!r}"
        )
    finally:
        _cleanup_example(example)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_response_allows_extra_fields(example, monkeypatch, tmp_path):
    """Each example's response is allowed to include extra fields (extensibility)."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)

        # Send a request with extra unknown fields — example must not crash
        augmented_request = {
            **CANONICAL_REQUEST,
            "future_nexo_field": "some_value",
            "experimental": {"feature_flag": True},
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=augmented_request)

        assert resp.status_code == 200, (
            f"Example '{example['id']}' crashed on request with extra fields: {resp.text}"
        )
    finally:
        _cleanup_example(example)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_cards_comply_if_present(example, monkeypatch, tmp_path):
    """If an example returns cards, each card must have a non-empty 'type'."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=CANONICAL_REQUEST)

        assert resp.status_code == 200
        data = resp.json()
        cards = data.get("cards")
        if cards is not None:
            assert isinstance(cards, list), (
                f"Example '{example['id']}': 'cards' must be a list"
            )
            for i, card in enumerate(cards):
                assert isinstance(card, dict), (
                    f"Example '{example['id']}': card[{i}] must be a dict"
                )
                assert card.get("type"), (
                    f"Example '{example['id']}': card[{i}] missing required 'type' field"
                )
    finally:
        _cleanup_example(example)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", WEBHOOK_EXAMPLES, ids=[e["id"] for e in WEBHOOK_EXAMPLES])
async def test_example_actions_comply_if_present(example, monkeypatch, tmp_path):
    """If an example returns actions, each action must have 'id' and 'label'."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    try:
        app = _load_example_app(example, monkeypatch, tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(example["endpoint"], json=CANONICAL_REQUEST)

        assert resp.status_code == 200
        data = resp.json()
        actions = data.get("actions")
        if actions is not None:
            assert isinstance(actions, list), (
                f"Example '{example['id']}': 'actions' must be a list"
            )
            for i, action in enumerate(actions):
                assert isinstance(action, dict), (
                    f"Example '{example['id']}': action[{i}] must be a dict"
                )
                assert action.get("id"), (
                    f"Example '{example['id']}': action[{i}] missing required 'id' field"
                )
                assert action.get("label"), (
                    f"Example '{example['id']}': action[{i}] missing required 'label' field"
                )
                style = action.get("style")
                if style is not None:
                    assert style in {"primary", "secondary"}, (
                        f"Example '{example['id']}': action[{i}] style must be "
                        f"'primary' or 'secondary', got {style!r}"
                    )
    finally:
        _cleanup_example(example)
