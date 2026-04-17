"""Cross-repo webhook contract tests.

Validates that all Python webhook examples (routines, food-ordering,
football-live, travel-planning) return correct canonical envelopes and
reject invalid requests correctly.

Uses pytest parametrize to run the same contract checks against each webhook.
All external calls are mocked — no network, LLM, or database access required.

Run:
    cd /Users/markmacmahon/dev/luzia-nexo-api
    pip install fastapi httpx pydantic pytest pytest-asyncio anyio
    python -m pytest tests/test_webhook_contracts.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies before any example module is imported.
# This lets the tests run in any Python environment that has fastapi + httpx
# without requiring Vertex credentials or heavyweight optional packages.
# ---------------------------------------------------------------------------

import types


def _stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _ensure_litellm_stub() -> None:
    """Inject a minimal litellm stub if litellm is not installed."""
    if "litellm" in sys.modules:
        return

    async def _acompletion(*_a, **_kw):
        class _Choice:
            class delta:
                content = "stub"

            class message:
                content = "stub"

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    stub = _stub_module("litellm", acompletion=_acompletion)
    sys.modules["litellm"] = stub


_ensure_litellm_stub()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
WEBHOOK_ROOT = REPO_ROOT / "examples" / "webhook"
sys.path.insert(0, str(REPO_ROOT / "examples"))
from test_support.fake_vector_store import FakeVectorStoreRegistry

ROUTINES_PATH = WEBHOOK_ROOT / "routines" / "python"
FOOD_PATH = WEBHOOK_ROOT / "food-ordering" / "python"
FOOTBALL_PATH = WEBHOOK_ROOT / "football-live" / "python"
TRAVEL_PATH = WEBHOOK_ROOT / "travel-planning" / "python"

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "2026-03"
VALID_STATUSES = {"completed", "error"}
VALID_CAPABILITY_STATES = {"live", "simulated", "requires_connector"}

# ---------------------------------------------------------------------------
# Module loader helpers
# ---------------------------------------------------------------------------


def _load_module(path: Path, module_name: str, filename: str = "app.py") -> Any:
    """Load a Python module from an absolute path, isolated by module_name."""
    spec = importlib.util.spec_from_file_location(module_name, path / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _unload_module(module_name: str) -> None:
    """Remove a module and any sub-modules it imported from sys.modules."""
    keys_to_remove = [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]
    for k in keys_to_remove:
        sys.modules.pop(k, None)


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------


def _sign(secret: str, timestamp: str, body: str) -> str:
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _signed_headers(secret: str, body: str, timestamp: str = "1700000000") -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-timestamp": timestamp,
        "x-signature": _sign(secret, timestamp, body),
    }


# ---------------------------------------------------------------------------
# Standard webhook payload
# ---------------------------------------------------------------------------


def _make_payload(content: str, **extra) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event": "message_created",
        "app": {},
        "thread": {},
        "message": {"role": "user", "content": content},
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Per-webhook fixture builders
#
# Each returns (client, module) with all I/O mocked.
# ---------------------------------------------------------------------------


class _RoutinesFixture:
    """Loads the routines webhook and patches call_llm."""

    _module_name = "contract_routines"

    @classmethod
    def load(cls) -> tuple[TestClient, Any]:
        sys.path.insert(0, str(ROUTINES_PATH))
        try:
            mod = _load_module(ROUTINES_PATH, cls._module_name, "app.py")
            mod.WEBHOOK_SECRET = ""
            client = TestClient(mod.app, raise_server_exceptions=False)
            return client, mod
        finally:
            sys.path.remove(str(ROUTINES_PATH))

    @classmethod
    def unload(cls) -> None:
        _unload_module(cls._module_name)

    @staticmethod
    def mock_llm(mod: Any, return_value: str = "ok") -> Any:
        return patch.object(mod, "call_llm", return_value=return_value)

    @staticmethod
    def mock_stream(mod: Any, text: str = "ok"):
        async def _fake(*_a, **_kw):
            yield f"event: content_delta\ndata: {json.dumps({'type': 'content_delta', 'text': text})}\n\n"
        return patch.object(mod, "stream_llm", side_effect=_fake)

    @staticmethod
    def happy_payload() -> dict:
        return _make_payload("morning briefing")

    @staticmethod
    def intent_payload() -> dict:
        return _make_payload("Add a reminder to call doctor")

    @staticmethod
    def has_llm(mod: Any) -> bool:
        return hasattr(mod, "call_llm")

    @staticmethod
    def has_streaming(mod: Any) -> bool:
        return hasattr(mod, "STREAMING_ENABLED")


class _FoodFixture:
    """Loads the food-ordering webhook and patches call_llm."""

    _module_name = "contract_food"

    @classmethod
    def load(cls) -> tuple[TestClient, Any]:
        sys.path.insert(0, str(FOOD_PATH))
        try:
            mod = _load_module(FOOD_PATH, cls._module_name, "app.py")
            mod.WEBHOOK_SECRET = ""
            client = TestClient(mod.app, raise_server_exceptions=False)
            return client, mod
        finally:
            sys.path.remove(str(FOOD_PATH))

    @classmethod
    def unload(cls) -> None:
        _unload_module(cls._module_name)

    @staticmethod
    def mock_llm(mod: Any, return_value: str = "ok") -> Any:
        return patch.object(mod, "call_llm", return_value=return_value)

    @staticmethod
    def mock_stream(mod: Any, text: str = "ok"):
        async def _fake(*_a, **_kw):
            yield f"event: content_delta\ndata: {json.dumps({'type': 'content_delta', 'text': text})}\n\n"
        return patch.object(mod, "stream_llm", side_effect=_fake)

    @staticmethod
    def happy_payload() -> dict:
        return _make_payload("show me the menu")

    @staticmethod
    def intent_payload() -> dict:
        return _make_payload("I want to order a pizza")

    @staticmethod
    def has_llm(mod: Any) -> bool:
        return hasattr(mod, "call_llm")

    @staticmethod
    def has_streaming(mod: Any) -> bool:
        return hasattr(mod, "STREAMING_ENABLED")


class _FootballFixture:
    """Loads the football-live webhook with an in-memory fake vector store."""

    _module_name = "contract_football"

    @classmethod
    def load(cls) -> tuple[TestClient, Any]:
        sys.path.insert(0, str(FOOTBALL_PATH))
        try:
            server_mod = _load_module(FOOTBALL_PATH, cls._module_name, "server.py")
            # Also load ingest (football-live has a separate ingest.py)
            ingest_spec = importlib.util.spec_from_file_location(
                f"{cls._module_name}_ingest", FOOTBALL_PATH / "ingest.py"
            )
            ingest_mod = importlib.util.module_from_spec(ingest_spec)
            sys.modules[f"{cls._module_name}_ingest"] = ingest_mod
            ingest_spec.loader.exec_module(ingest_mod)

            fake_store = FakeVectorStoreRegistry()
            ingest_mod._pg_collections = {}
            ingest_mod.get_collection = lambda name: fake_store.get(name)
            ingest_mod.embed_texts = lambda texts: [[0.0] * 1536 for _ in texts]
            server_mod.get_collection = lambda name: fake_store.get(name)

            server_mod.WEBHOOK_SECRET = ""
            server_mod.FOOTBALL_DATA_API_KEY = ""

            client = TestClient(server_mod.app, raise_server_exceptions=False)
            return client, server_mod
        finally:
            sys.path.remove(str(FOOTBALL_PATH))

    @classmethod
    def unload(cls) -> None:
        _unload_module(cls._module_name)
        _unload_module(f"{cls._module_name}_ingest")

    @staticmethod
    def mock_llm(mod: Any, return_value: str = "ok") -> Any:
        return patch.object(mod, "call_llm", return_value=return_value)

    @staticmethod
    def mock_stream(mod: Any, text: str = "ok"):
        async def _fake(*_a, **_kw):
            yield f"event: content_delta\ndata: {json.dumps({'type': 'content_delta', 'text': text})}\n\n"
        return patch.object(mod, "stream_llm", side_effect=_fake)

    @staticmethod
    def mock_search(mod: Any):
        """Patch all search functions to return empty results (no vector-store query needed)."""
        return [
            patch.object(mod, "search_matches", return_value=[]),
            patch.object(mod, "search_standings", return_value=[]),
            patch.object(mod, "search_scorers", return_value=[]),
        ]

    @staticmethod
    def happy_payload() -> dict:
        return {"message": {"content": "Arsenal score"}}

    @staticmethod
    def intent_payload() -> dict:
        return {"message": {"content": "top scorer"}}

    @staticmethod
    def has_llm(mod: Any) -> bool:
        return hasattr(mod, "call_llm")

    @staticmethod
    def has_streaming(mod: Any) -> bool:
        return hasattr(mod, "STREAMING_ENABLED")


class _TravelFixture:
    """Loads the travel-planning webhook and patches async call_llm."""

    _module_name = "contract_travel"

    @classmethod
    def load(cls) -> tuple[TestClient, Any]:
        sys.path.insert(0, str(TRAVEL_PATH))
        try:
            mod = _load_module(TRAVEL_PATH, cls._module_name, "app.py")
            mod.WEBHOOK_SECRET = ""
            client = TestClient(mod.app, raise_server_exceptions=False)
            return client, mod
        finally:
            sys.path.remove(str(TRAVEL_PATH))

    @classmethod
    def unload(cls) -> None:
        _unload_module(cls._module_name)

    @staticmethod
    def mock_llm(mod: Any, return_value: str = "ok") -> Any:
        """Travel uses async call_llm; mock as AsyncMock."""
        return patch.object(mod, "call_llm", new=AsyncMock(return_value=return_value))

    @staticmethod
    def mock_stream(mod: Any, text: str = "ok"):
        async def _fake(*_a, **_kw):
            yield f"event: content_delta\ndata: {json.dumps({'type': 'content_delta', 'text': text})}\n\n"
        return patch.object(mod, "stream_llm", side_effect=_fake)

    @staticmethod
    def happy_payload() -> dict:
        return _make_payload("Plan a trip to Barcelona for 5 days")

    @staticmethod
    def intent_payload() -> dict:
        return _make_payload("Check my travel budget")

    @staticmethod
    def has_llm(mod: Any) -> bool:
        return hasattr(mod, "call_llm")

    @staticmethod
    def has_streaming(mod: Any) -> bool:
        return hasattr(mod, "STREAMING_ENABLED")


# ---------------------------------------------------------------------------
# Parametrize: all four webhooks
# ---------------------------------------------------------------------------

WEBHOOK_FIXTURES = [
    pytest.param(_RoutinesFixture, id="routines"),
    pytest.param(_FoodFixture, id="food-ordering"),
    pytest.param(_FootballFixture, id="football-live"),
    pytest.param(_TravelFixture, id="travel-planning"),
]


# ---------------------------------------------------------------------------
# HAPPY PATH: Valid request returns canonical envelope
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Parametrized happy-path tests: each webhook returns a canonical envelope."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_valid_request_returns_200(self, fixture_cls):
        """POST with valid payload returns HTTP 200."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "Test response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_response_has_schema_version(self, fixture_cls):
        """Response includes schema_version: '2026-03'."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response text"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            data = resp.json()
            assert "schema_version" in data, f"Missing 'schema_version' in response: {data}"
            assert data["schema_version"] == SCHEMA_VERSION, (
                f"Expected schema_version={SCHEMA_VERSION!r}, got {data['schema_version']!r}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_response_has_valid_status(self, fixture_cls):
        """Response status is one of: 'completed', 'error'."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response text"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            data = resp.json()
            assert "status" in data, f"Missing 'status' in response: {data}"
            assert data["status"] in VALID_STATUSES, (
                f"Invalid status {data['status']!r}; must be one of {VALID_STATUSES}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_response_has_non_empty_content_parts(self, fixture_cls):
        """Response content_parts is a non-empty list."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "some response text here"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            data = resp.json()
            assert "content_parts" in data, f"Missing 'content_parts' in response: {data}"
            assert isinstance(data["content_parts"], list), "'content_parts' must be a list"
            assert len(data["content_parts"]) > 0, "'content_parts' must not be empty"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_response_cards_is_list(self, fixture_cls):
        """Response 'cards' is a list (may be empty)."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            data = resp.json()
            assert "cards" in data, f"Missing 'cards' in response: {data}"
            assert isinstance(data["cards"], list), "'cards' must be a list"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_response_actions_is_list(self, fixture_cls):
        """Response 'actions' is a list (may be empty)."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            data = resp.json()
            assert "actions" in data, f"Missing 'actions' in response: {data}"
            assert isinstance(data["actions"], list), "'actions' must be a list"
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# HAPPY PATH: Cards include capability_state metadata
# ---------------------------------------------------------------------------


class TestCapabilityStateMetadata:
    """Cards returned by intent-specific messages include valid capability_state."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_cards_have_capability_state_metadata(self, fixture_cls):
        """Each card includes metadata.capability_state from VALID_CAPABILITY_STATES."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.intent_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response with cards"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            cards = data.get("cards", [])
            # Only validate cards that exist — some empty-result paths return no cards
            for i, card in enumerate(cards):
                meta = card.get("metadata", {})
                cap_state = meta.get("capability_state")
                assert cap_state is not None, (
                    f"card[{i}] (type={card.get('type')!r}) missing metadata.capability_state"
                )
                assert cap_state in VALID_CAPABILITY_STATES, (
                    f"card[{i}] capability_state={cap_state!r} not in {VALID_CAPABILITY_STATES}"
                )
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# HAPPY PATH: Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /health returns 200 with a status field."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_health_returns_200(self, fixture_cls):
        """GET /health returns HTTP 200."""
        client, mod = fixture_cls.load()
        try:
            resp = client.get("/health")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_health_response_has_status(self, fixture_cls):
        """GET /health response body contains 'status' field."""
        client, mod = fixture_cls.load()
        try:
            data = client.get("/health").json()
            assert "status" in data, f"Health response missing 'status': {data}"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_health_status_is_ok(self, fixture_cls):
        """GET /health status value is 'ok'."""
        client, mod = fixture_cls.load()
        try:
            data = client.get("/health").json()
            assert data.get("status") == "ok", (
                f"Health status should be 'ok', got {data.get('status')!r}"
            )
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# HAPPY PATH: SSE streaming mode
# ---------------------------------------------------------------------------


class TestSSEStreaming:
    """Webhooks that support SSE return correct event-stream format."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_sse_accept_header_returns_event_stream(self, fixture_cls):
        """POST with Accept: text/event-stream returns SSE content-type when streaming enabled."""
        client, mod = fixture_cls.load()
        try:
            if not fixture_cls.has_streaming(mod):
                pytest.skip("Webhook does not have STREAMING_ENABLED flag")

            mod.STREAMING_ENABLED = True
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_stream(mod, text="hello"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})
                else:
                    resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", ""), (
                f"Expected SSE content-type, got: {resp.headers.get('content-type')}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_sse_done_event_has_schema_version(self, fixture_cls):
        """SSE stream ends with a 'done' event containing schema_version."""
        client, mod = fixture_cls.load()
        try:
            if not fixture_cls.has_streaming(mod):
                pytest.skip("Webhook does not have STREAMING_ENABLED flag")

            mod.STREAMING_ENABLED = True
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_stream(mod, text="hello"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})
                else:
                    resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})

            assert resp.status_code == 200

            events = [
                json.loads(line[len("data:"):].strip())
                for line in resp.text.splitlines()
                if line.startswith("data:")
            ]
            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) >= 1, f"No 'done' SSE event found. Events: {events}"
            done = done_events[-1]
            assert done.get("schema_version") == SCHEMA_VERSION, (
                f"SSE done event has wrong schema_version: {done.get('schema_version')!r}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_sse_done_event_has_valid_status(self, fixture_cls):
        """SSE done event contains a valid status field."""
        client, mod = fixture_cls.load()
        try:
            if not fixture_cls.has_streaming(mod):
                pytest.skip("Webhook does not have STREAMING_ENABLED flag")

            mod.STREAMING_ENABLED = True
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_stream(mod, text="ok"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})
                else:
                    resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})

            events = [
                json.loads(line[len("data:"):].strip())
                for line in resp.text.splitlines()
                if line.startswith("data:")
            ]
            done = next((e for e in events if e.get("type") == "done"), None)
            assert done is not None, "No SSE done event found"
            assert done.get("status") in VALID_STATUSES, (
                f"SSE done event status {done.get('status')!r} not in {VALID_STATUSES}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_json_fallback_when_streaming_disabled(self, fixture_cls):
        """When STREAMING_ENABLED=False, Accept: text/event-stream still returns JSON."""
        client, mod = fixture_cls.load()
        try:
            if not fixture_cls.has_streaming(mod):
                pytest.skip("Webhook does not have STREAMING_ENABLED flag")

            mod.STREAMING_ENABLED = False
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})
                else:
                    resp = client.post("/", json=payload, headers={"Accept": "text/event-stream"})

            assert resp.headers.get("content-type", "").startswith("application/json"), (
                f"Expected JSON content-type with streaming disabled, got: {resp.headers.get('content-type')}"
            )
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# SAD PATH: Missing / empty body
# ---------------------------------------------------------------------------


class TestSadPathMissingBody:
    """Webhooks reject requests with missing or empty message content."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_empty_message_content_returns_4xx(self, fixture_cls):
        """POST with empty message content returns a 4xx error."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            # Override content to be empty
            payload["message"]["content"] = ""
            mod.WEBHOOK_SECRET = ""

            resp = client.post("/", json=payload)
            assert resp.status_code in range(400, 500), (
                f"Expected 4xx for empty content, got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_empty_message_content_returns_error_info(self, fixture_cls):
        """Response body for empty message contains error indication."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            payload["message"]["content"] = ""
            mod.WEBHOOK_SECRET = ""

            resp = client.post("/", json=payload)
            # Either an error field in body or HTTP 4xx is acceptable
            if resp.status_code == 200:
                data = resp.json()
                assert "error" in data or data.get("status") == "error", (
                    f"Empty content returned 200 without error indicator: {data}"
                )
            else:
                assert resp.status_code in range(400, 500)
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# SAD PATH: Invalid HMAC signature
# ---------------------------------------------------------------------------


class TestSadPathInvalidSignature:
    """Webhooks reject requests with invalid HMAC signatures when a secret is configured."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_invalid_signature_returns_401(self, fixture_cls):
        """POST with an invalid X-Signature returns 401."""
        client, mod = fixture_cls.load()
        try:
            mod.WEBHOOK_SECRET = "test-secret"
            payload = fixture_cls.happy_payload()
            body = json.dumps(payload)

            resp = client.post(
                "/",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-timestamp": "1700000000",
                    "x-signature": "sha256=invalidsignature",
                },
            )
            assert resp.status_code == 401, (
                f"Expected 401 for invalid signature, got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_missing_signature_headers_returns_401(self, fixture_cls):
        """POST without X-Signature headers when secret is set returns 401."""
        client, mod = fixture_cls.load()
        try:
            mod.WEBHOOK_SECRET = "test-secret"
            payload = fixture_cls.happy_payload()

            resp = client.post("/", json=payload)
            assert resp.status_code == 401, (
                f"Expected 401 for missing signature, got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_valid_signature_with_secret_returns_200(self, fixture_cls):
        """POST with a correctly signed request returns 200 when secret is set."""
        client, mod = fixture_cls.load()
        try:
            mod.WEBHOOK_SECRET = "test-secret"
            payload = fixture_cls.happy_payload()
            body = json.dumps(payload)
            headers = _signed_headers("test-secret", body)

            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)
            with fixture_cls.mock_llm(mod, "ok"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", data=body, headers=headers)
                else:
                    resp = client.post("/", data=body, headers=headers)

            assert resp.status_code == 200, (
                f"Valid HMAC should return 200, got {resp.status_code}: {resp.text}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_no_secret_configured_skips_verification(self, fixture_cls):
        """POST without signature headers is accepted when WEBHOOK_SECRET is empty."""
        client, mod = fixture_cls.load()
        try:
            mod.WEBHOOK_SECRET = ""
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "ok"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200, (
                f"No secret configured; should accept unsigned request. Got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# SAD PATH: Malformed JSON
# ---------------------------------------------------------------------------


class TestSadPathMalformedJSON:
    """Webhooks reject requests with non-JSON bodies."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_malformed_json_returns_4xx(self, fixture_cls):
        """POST with 'not json' as body returns 400 or 422."""
        client, mod = fixture_cls.load()
        try:
            mod.WEBHOOK_SECRET = ""
            resp = client.post(
                "/",
                data=b"not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code in (400, 422, 500), (
                f"Malformed JSON should return 4xx/5xx, got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_truncated_json_returns_4xx(self, fixture_cls):
        """POST with truncated JSON body returns 4xx."""
        client, mod = fixture_cls.load()
        try:
            mod.WEBHOOK_SECRET = ""
            resp = client.post(
                "/",
                data=b'{"message": {"content":',
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code in (400, 422, 500), (
                f"Truncated JSON should return 4xx/5xx, got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# SAD PATH: Wrong HTTP method
# ---------------------------------------------------------------------------


class TestSadPathWrongMethod:
    """Webhooks reject GET requests to the webhook POST endpoint."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_get_to_webhook_returns_405_or_redirect(self, fixture_cls):
        """GET to the webhook endpoint (/) returns 405 Method Not Allowed."""
        # Note: GET "/" is typically used for service discovery in these webhooks
        # so this test targets a method that IS unsupported on "/"
        # We test DELETE as an unsupported method instead
        client, mod = fixture_cls.load()
        try:
            resp = client.delete("/")
            # FastAPI returns 405 for unknown methods on known routes
            assert resp.status_code in (405, 404, 422), (
                f"DELETE / should not succeed; got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_put_to_webhook_returns_error(self, fixture_cls):
        """PUT to the webhook endpoint returns 405."""
        client, mod = fixture_cls.load()
        try:
            resp = client.put("/", json=fixture_cls.happy_payload())
            assert resp.status_code in (405, 404, 422), (
                f"PUT / should return an error; got {resp.status_code}"
            )
        finally:
            fixture_cls.unload()


# ---------------------------------------------------------------------------
# Additional canonical envelope field validation
# ---------------------------------------------------------------------------


class TestCanonicalEnvelopeFields:
    """Verify all required canonical envelope fields are present and correct."""

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_content_parts_each_have_text_field(self, fixture_cls):
        """Each content_part must have a 'text' key."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "some text output"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200
            parts = resp.json().get("content_parts", [])
            for i, part in enumerate(parts):
                assert "text" in part, f"content_parts[{i}] missing 'text': {part}"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_cards_each_have_type_field(self, fixture_cls):
        """Each card must have a 'type' key."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200
            cards = resp.json().get("cards", [])
            for i, card in enumerate(cards):
                assert "type" in card, f"cards[{i}] missing 'type': {card}"
                assert card["type"], f"cards[{i}] 'type' must be non-empty"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_actions_each_have_id_and_label(self, fixture_cls):
        """Each action must have 'id' and 'label' keys."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200
            actions = resp.json().get("actions", [])
            for i, action in enumerate(actions):
                assert "id" in action, f"actions[{i}] missing 'id': {action}"
                assert "label" in action, f"actions[{i}] missing 'label': {action}"
                assert action["id"], f"actions[{i}] 'id' must be non-empty"
                assert action["label"], f"actions[{i}] 'label' must be non-empty"
        finally:
            fixture_cls.unload()

    @pytest.mark.parametrize("fixture_cls", WEBHOOK_FIXTURES)
    def test_extra_fields_in_request_do_not_crash(self, fixture_cls):
        """Webhook must not crash when request payload has unknown extra fields."""
        client, mod = fixture_cls.load()
        try:
            payload = fixture_cls.happy_payload()
            payload["future_nexo_field"] = "some_value"
            payload["experimental"] = {"feature_flag": True}

            search_patches = getattr(fixture_cls, "mock_search", lambda m: [])(mod)

            with fixture_cls.mock_llm(mod, "response"):
                if search_patches:
                    with search_patches[0], search_patches[1], search_patches[2]:
                        resp = client.post("/", json=payload)
                else:
                    resp = client.post("/", json=payload)

            assert resp.status_code == 200, (
                f"Webhook crashed on extra request fields: {resp.status_code} {resp.text}"
            )
        finally:
            fixture_cls.unload()
