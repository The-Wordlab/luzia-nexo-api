"""
Tests for the language-tutor webhook.

Covers:
- Root / health endpoints
- Intent detection (phrase_help, quiz, lesson_plan, fallback)
- Language detection (Italian, Spanish, Portuguese)
- phrase_help happy path - card structure and language
- quiz happy path - card structure
- lesson_plan happy path - 4-week plan fields
- Fallback intent defaults to phrase_help
- Malformed payload (empty message, missing message key, invalid JSON)
- HMAC signature verification (valid, invalid, missing)

Run with:
    pytest test_language_tutor.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Isolated module import — avoids collision when pytest runs multiple webhook
# test files in the same process (each has its own app.py).
# ---------------------------------------------------------------------------
_APP_DIR = Path(__file__).resolve().parent
_MODULE_NAME = "language_tutor_app"


def _load_tutor_app():
    """Load (or reload) the language-tutor app.py with full isolation."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _APP_DIR / "app.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


# Initial load for unit tests that don't need env-var reload
_tutor_mod = _load_tutor_app()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sign(secret: str, timestamp: str, body: str) -> str:
    """Compute HMAC-SHA256 signature in the format expected by the server."""
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "sha256=" + digest


def _payload(content: str) -> dict:
    return {
        "event": "message_created",
        "app": {},
        "thread": {},
        "message": {"role": "user", "content": content},
    }


def _card(data: dict) -> dict:
    cards = data.get("cards", [])
    assert cards, "Expected at least one card in response"
    return cards[0]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_module(monkeypatch):
    """Load app module with WEBHOOK_SECRET unset (open mode) and LLM mocked."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("STREAMING_ENABLED", "false")
    return _load_tutor_app()


@pytest.fixture
def open_app(app_module):
    """FastAPI app with no secret, streaming disabled."""
    return app_module.app


@pytest.fixture
def secret_app(monkeypatch):
    """FastAPI app with WEBHOOK_SECRET=testsecret, streaming disabled."""
    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    monkeypatch.setenv("STREAMING_ENABLED", "false")
    mod = _load_tutor_app()
    return mod.app


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_endpoint(open_app):
    """GET / returns service metadata."""
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "webhook-language-tutor-python"
    assert "capabilities" in data
    assert data["schema_version"] == "2026-03-01"


@pytest.mark.asyncio
async def test_health_endpoint(open_app):
    """GET /health returns ok status."""
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


# ---------------------------------------------------------------------------
# Intent detection (unit tests - no HTTP)
# ---------------------------------------------------------------------------


def test_detect_intent_phrase_help(app_module):
    assert app_module.detect_intent("How do I say hello in Italian?") == "phrase_help"
    assert app_module.detect_intent("Teach me to order food in Spanish") == "phrase_help"
    assert app_module.detect_intent("I need a phrase for introducing myself") == "phrase_help"


def test_detect_intent_quiz(app_module):
    assert app_module.detect_intent("Give me a quick Spanish conversation quiz") == "quiz"
    assert app_module.detect_intent("Test me on Portuguese vocabulary") == "quiz"
    assert app_module.detect_intent("Let me practice with a quiz") == "quiz"


def test_detect_intent_lesson_plan(app_module):
    assert app_module.detect_intent("Create a beginner lesson plan for Italian") == "lesson_plan"
    assert app_module.detect_intent("I want a weekly study plan") == "lesson_plan"
    assert app_module.detect_intent("Build a curriculum for Spanish learners") == "lesson_plan"


def test_detect_intent_fallback_defaults_to_phrase_help(app_module):
    """Unknown messages default to phrase_help (not quiz or lesson_plan)."""
    assert app_module.detect_intent("Hello there") == "phrase_help"
    assert app_module.detect_intent("What should I eat today?") == "phrase_help"


def test_detect_intent_quiz_beats_single_phrase_help_keyword(app_module):
    """Quiz wins when it has equal or higher keyword count than phrase_help."""
    # "quiz" matches quiz(1), "test me" matches quiz(1) -> quiz wins
    result = app_module.detect_intent("quiz and test me")
    assert result == "quiz"


# ---------------------------------------------------------------------------
# Language detection (unit tests)
# ---------------------------------------------------------------------------


def test_detect_language_italian(app_module):
    assert app_module._detect_language("order food in Italian") == "Italian"
    assert app_module._detect_language("Italian phrases please") == "Italian"


def test_detect_language_spanish(app_module):
    assert app_module._detect_language("Spanish conversation quiz") == "Spanish"
    assert app_module._detect_language("learn Spanish") == "Spanish"


def test_detect_language_portuguese(app_module):
    assert app_module._detect_language("How do I say hello in Portuguese?") == "Portuguese"
    assert app_module._detect_language("portuguese study plan") == "Portuguese"


def test_detect_language_defaults_to_spanish(app_module):
    """When no language is detected, defaults to Spanish."""
    assert app_module._detect_language("just a random phrase") == "Spanish"
    assert app_module._detect_language("") == "Spanish"


# ---------------------------------------------------------------------------
# phrase_help happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phrase_help_italian(open_app):
    """phrase_help for Italian returns Italian card with correct phrase."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Phrase support text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Teach me to order food in Italian"))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["schema_version"] == "2026-03-01"
    card = _card(data)
    assert card["type"] == "phrase_help"
    assert "Italian" in card["title"]
    # Italian phrase should be present
    field_values = [f["value"] for f in card["fields"]]
    assert any("favore" in v or "pasta" in v or "ordinare" in v for v in field_values)


@pytest.mark.asyncio
async def test_phrase_help_spanish(open_app):
    """phrase_help for Spanish returns Spanish card with correct phrase."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Phrase support text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("How do I say something in Spanish?"))
    assert r.status_code == 200
    card = _card(r.json())
    assert card["type"] == "phrase_help"
    assert "Spanish" in card["title"]
    field_values = [f["value"] for f in card["fields"]]
    assert any("favor" in v or "cena" in v or "pedir" in v for v in field_values)


@pytest.mark.asyncio
async def test_phrase_help_portuguese(open_app):
    """phrase_help for Portuguese returns Portuguese card with correct phrase."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Phrase support text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Teach me a phrase in Portuguese please"))
    assert r.status_code == 200
    card = _card(r.json())
    assert card["type"] == "phrase_help"
    assert "Portuguese" in card["title"]
    field_values = [f["value"] for f in card["fields"]]
    assert any("jantar" in v or "pedir" in v or "favor" in v for v in field_values)


@pytest.mark.asyncio
async def test_phrase_help_card_has_required_fields(open_app):
    """phrase_help card has title, subtitle, badges, fields, and metadata."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("How do I say goodbye in Spanish?"))
    card = _card(r.json())
    assert card["type"] == "phrase_help"
    assert "title" in card
    assert "subtitle" in card
    assert isinstance(card["badges"], list)
    assert len(card["fields"]) == 3
    assert card["metadata"]["capability_state"] == "live"


@pytest.mark.asyncio
async def test_phrase_help_actions(open_app):
    """phrase_help response includes practice and more_variants actions."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("How do I say goodbye in Spanish?"))
    data = r.json()
    action_ids = [a["id"] for a in data["actions"]]
    assert "practice" in action_ids
    assert "more_variants" in action_ids


# ---------------------------------------------------------------------------
# quiz happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quiz_card_structure(open_app):
    """quiz intent returns a quiz card with 3 fields and correct structure."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Quiz text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Give me a Spanish conversation quiz"))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    card = _card(data)
    assert card["type"] == "quiz"
    assert "Spanish" in card["title"]
    assert "subtitle" in card
    assert len(card["fields"]) == 3
    field_labels = [f["label"] for f in card["fields"]]
    assert "Prompt 1" in field_labels
    assert "Prompt 2" in field_labels
    assert "Scoring" in field_labels
    assert card["metadata"]["capability_state"] == "live"


@pytest.mark.asyncio
async def test_quiz_actions(open_app):
    """quiz response includes start_quiz and show_answers actions."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Quiz text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Test me on Italian"))
    data = r.json()
    action_ids = [a["id"] for a in data["actions"]]
    assert "start_quiz" in action_ids
    assert "show_answers" in action_ids


@pytest.mark.asyncio
async def test_quiz_italian_language(open_app):
    """quiz for Italian uses Italian label."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Quiz text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Italian conversation quiz please"))
    card = _card(r.json())
    assert card["type"] == "quiz"
    assert "Italian" in card["title"]


# ---------------------------------------------------------------------------
# lesson_plan happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lesson_plan_card_structure(open_app):
    """lesson_plan intent returns a 4-week plan card."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Lesson plan text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Build a beginner lesson plan for Spanish"))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    card = _card(data)
    assert card["type"] == "lesson_plan"
    assert "Spanish" in card["title"]
    assert "4-Week" in card["title"]
    assert "subtitle" in card
    assert len(card["fields"]) == 4
    field_labels = [f["label"] for f in card["fields"]]
    assert "Week 1" in field_labels
    assert "Week 2" in field_labels
    assert "Week 3" in field_labels
    assert "Week 4" in field_labels
    assert card["metadata"]["capability_state"] == "live"


@pytest.mark.asyncio
async def test_lesson_plan_actions(open_app):
    """lesson_plan response includes begin_week1 and adapt_level actions."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Lesson plan text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Create a weekly Italian study plan"))
    data = r.json()
    action_ids = [a["id"] for a in data["actions"]]
    assert "begin_week1" in action_ids
    assert "adapt_level" in action_ids


@pytest.mark.asyncio
async def test_lesson_plan_portuguese(open_app):
    """lesson_plan for Portuguese uses Portuguese label."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Lesson plan text"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Give me a beginner Portuguese curriculum"))
    card = _card(r.json())
    assert card["type"] == "lesson_plan"
    assert "Portuguese" in card["title"]


# ---------------------------------------------------------------------------
# Profile personalisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_name_prepended_to_reply(open_app):
    """When profile.display_name is set, reply starts with 'Hey <name>'."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Here is your phrase."):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post(
                "/",
                json={
                    **_payload("How do I order food in Italian?"),
                    "profile": {"display_name": "Elena"},
                },
            )
    data = r.json()
    text_parts = [p["text"] for p in data.get("content_parts", []) if p.get("type") == "text"]
    combined = " ".join(text_parts)
    assert "Elena" in combined


@pytest.mark.asyncio
async def test_no_greeting_without_display_name(open_app):
    """When no profile is set, reply does not crash and returns content_parts."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Here is your phrase."):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("How do I say hello in Spanish?"))
    assert r.status_code == 200
    data = r.json()
    assert "content_parts" in data


# ---------------------------------------------------------------------------
# Malformed payloads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_message_returns_400(open_app):
    """An empty message content string returns 400."""
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        r = await client.post("/", json=_payload(""))
    assert r.status_code == 400
    assert "error" in r.json()


@pytest.mark.asyncio
async def test_missing_message_key_returns_400(open_app):
    """A payload without a message key returns 400."""
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        r = await client.post("/", json={"event": "message_created"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_invalid_json_returns_error(open_app):
    """Sending non-JSON body returns an error (4xx or 5xx)."""
    # The app uses json.loads() directly without try/except, so a malformed
    # body raises JSONDecodeError which FastAPI surfaces as a 500.
    async with AsyncClient(
        transport=ASGITransport(app=open_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/",
            content=b"not valid json at all!!!",
            headers={"content-type": "application/json"},
        )
    assert r.status_code >= 400


# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_signature_accepted(secret_app):
    """A correctly signed request passes the signature gate."""
    body = json.dumps(_payload("Teach me a phrase in Italian"))
    ts = "1700000000"
    sig = _sign("testsecret", ts, body)
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
            r = await client.post(
                "/",
                content=body.encode(),
                headers={
                    "content-type": "application/json",
                    "x-timestamp": ts,
                    "x-signature": sig,
                },
            )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(secret_app):
    """A request with a wrong signature is rejected with 401."""
    body = json.dumps(_payload("quiz me on Spanish"))
    async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
        r = await client.post(
            "/",
            content=body.encode(),
            headers={
                "content-type": "application/json",
                "x-timestamp": "1700000000",
                "x-signature": "sha256=deadbeefdeadbeefdeadbeefdeadbeef",
            },
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_signature_returns_401(secret_app):
    """When WEBHOOK_SECRET is set, request without X-Signature is rejected."""
    body = json.dumps(_payload("lesson plan for Italian"))
    async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
        r = await client.post(
            "/",
            content=body.encode(),
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_timestamp_returns_401(secret_app):
    """When WEBHOOK_SECRET is set, request without X-Timestamp is rejected."""
    body = json.dumps(_payload("quiz me"))
    # Provide signature but no timestamp
    async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
        r = await client.post(
            "/",
            content=body.encode(),
            headers={
                "content-type": "application/json",
                "x-signature": "sha256=anything",
            },
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_secret_configured_accepts_unsigned_request(open_app):
    """When WEBHOOK_SECRET is not set, unsigned requests are accepted."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Teach me Italian phrases"))
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Response schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_schema_version(open_app):
    """All responses include the correct schema_version field."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Quiz me on Spanish"))
    assert r.json()["schema_version"] == "2026-03-01"


@pytest.mark.asyncio
async def test_response_status_completed(open_app):
    """Successful responses have status='completed'."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("lesson plan for Spanish beginners"))
    assert r.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_cards_always_present_in_response(open_app):
    """Every successful response includes exactly one card."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Teach me Spanish"))
    data = r.json()
    assert isinstance(data.get("cards"), list)
    assert len(data["cards"]) == 1


@pytest.mark.asyncio
async def test_actions_always_present_in_response(open_app):
    """Every successful response includes at least one action."""
    with patch("language_tutor_app.call_llm", new_callable=AsyncMock, return_value="Ok"):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            r = await client.post("/", json=_payload("Italian quiz"))
    data = r.json()
    assert isinstance(data.get("actions"), list)
    assert len(data["actions"]) >= 1
