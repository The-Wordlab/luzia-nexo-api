"""Tests for the Fitness Coach webhook.

Covers:
- workout_plan intent (happy path, beginner/intermediate/advanced level)
- progress_check intent (happy path, card fields, actions)
- nutrition_guidance intent (happy path, card fields, actions)
- fallback intent (unknown message defaults to workout_plan)
- malformed payload (empty message returns 400)
- HMAC signature verification (valid, invalid, missing)
- display_name personalisation
- metadata.capability_state == "live" on all cards
- AsyncClient + ASGITransport pattern

Run with:
    cd /Users/markmacmahon/dev/luzia-nexo-api
    uv run pytest examples/webhook/fitness-coach/python/test_fitness_coach.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Isolated module import — avoids collision when pytest runs multiple webhook
# test files in the same process (each has its own app.py).
# ---------------------------------------------------------------------------
_APP_DIR = Path(__file__).resolve().parent
_MODULE_NAME = "fitness_coach_app"


def _load_fitness_app():
    """Load (or reload) the fitness-coach app.py with full isolation."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _APP_DIR / "app.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


# Initial load for unit tests that don't need env-var reload
_fitness_mod = _load_fitness_app()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "2026-03"
TEST_SECRET = "testsecret"
TEST_TIMESTAMP = "1700000000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signature(secret: str, timestamp: str, body: bytes) -> str:
    """Compute the HMAC-SHA256 signature matching the server's expected format."""
    signed_payload = f"{timestamp}.{body.decode('utf-8')}"
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "sha256=" + digest


def _signed_headers(body: bytes, secret: str = TEST_SECRET, timestamp: str = TEST_TIMESTAMP) -> dict:
    return {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Signature": _make_signature(secret, timestamp, body),
    }


def _assert_success(data: dict) -> None:
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["status"] == "completed"
    assert data.get("task", {}).get("status") == "completed"
    assert data.get("capability", {}).get("name") == "fitness.coach"
    assert isinstance(data.get("artifacts"), list)
    assert isinstance(data.get("content_parts"), list)
    assert len(data["content_parts"]) > 0


def _assert_card(card: dict, expected_type: str) -> None:
    assert card["type"] == expected_type
    assert isinstance(card.get("title"), str) and card["title"]
    assert isinstance(card.get("badges"), list) and len(card["badges"]) > 0
    assert isinstance(card.get("fields"), list) and len(card["fields"]) > 0
    assert card.get("metadata", {}).get("capability_state") == "live"


# ---------------------------------------------------------------------------
# LLM mock — avoids real API calls in all tests
# ---------------------------------------------------------------------------


def _mock_acompletion(text: str = "Here is your fitness recommendation."):
    """Return an async mock for litellm.acompletion."""
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    result = SimpleNamespace(choices=[choice])
    return AsyncMock(return_value=result)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def open_app(monkeypatch):
    """FastAPI app with WEBHOOK_SECRET unset (open / dev mode)."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("STREAMING_ENABLED", "false")
    mod = _load_fitness_app()
    return mod.app


@pytest.fixture()
def secret_app(monkeypatch):
    """FastAPI app with WEBHOOK_SECRET=testsecret set."""
    monkeypatch.setenv("WEBHOOK_SECRET", TEST_SECRET)
    monkeypatch.setenv("STREAMING_ENABLED", "false")
    mod = _load_fitness_app()
    return mod.app


# ---------------------------------------------------------------------------
# Unit tests: detect_intent
# ---------------------------------------------------------------------------


def test_detect_intent_workout_plan():
    assert _fitness_mod.detect_intent("Design a 4-week workout plan") == "workout_plan"
    assert _fitness_mod.detect_intent("I need a beginner strength routine") == "workout_plan"


def test_detect_intent_progress_check():
    assert _fitness_mod.detect_intent("How am I doing this month?") == "progress_check"
    assert _fitness_mod.detect_intent("check my progress and results") == "progress_check"


def test_detect_intent_nutrition_guidance():
    assert _fitness_mod.detect_intent("What should I eat before workout?") == "nutrition_guidance"
    assert _fitness_mod.detect_intent("protein and nutrition advice") == "nutrition_guidance"


def test_detect_intent_fallback_defaults_to_workout_plan():
    assert _fitness_mod.detect_intent("hello there") == "workout_plan"
    assert _fitness_mod.detect_intent("good morning") == "workout_plan"


# ---------------------------------------------------------------------------
# GET / and /health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_returns_service_info(open_app):
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["service"] == "webhook-fitness-coach-python"


@pytest.mark.asyncio
async def test_health_returns_ok(open_app):
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_card_endpoint(open_app):
    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capabilities"]["items"][0]["name"] == "fitness.coach"


# ---------------------------------------------------------------------------
# Intent: workout_plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workout_plan_happy_path(open_app):
    """A workout-related message returns a complete workout_plan card."""
    body = json.dumps({"message": {"content": "I need a beginner workout plan"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    data = resp.json()
    _assert_success(data)
    assert isinstance(data.get("cards"), list) and len(data["cards"]) > 0
    _assert_card(data["cards"][0], "workout_plan")
    assert data["cards"][0]["title"] == "Your Training Plan"


@pytest.mark.asyncio
async def test_workout_plan_beginner_fields(open_app):
    """Beginner keyword produces a beginner-level plan; level appears in the field label."""
    body = json.dumps({"message": {"content": "I am a beginner looking for an exercise plan"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    card = resp.json()["cards"][0]
    assert card["type"] == "workout_plan"
    # The level is embedded in the field label: "Week plan (beginner)"
    label_text = " ".join(f["label"] for f in card["fields"])
    assert "beginner" in label_text.lower()


@pytest.mark.asyncio
async def test_workout_plan_intermediate_fields(open_app):
    """Intermediate keyword produces an intermediate-level plan; level appears in the field label."""
    body = json.dumps({"message": {"content": "intermediate training routine please"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    card = resp.json()["cards"][0]
    assert card["type"] == "workout_plan"
    label_text = " ".join(f["label"] for f in card["fields"])
    assert "intermediate" in label_text.lower()


@pytest.mark.asyncio
async def test_workout_plan_advanced_fields(open_app):
    """Advanced keyword produces an advanced-level plan; level appears in the field label."""
    # Use a message that clearly matches workout_plan intent and advanced level
    # Avoid words like "program" which contain "pr" (a progress_check keyword)
    body = json.dumps({"message": {"content": "advanced athlete hypertrophy split workout routine"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    card = resp.json()["cards"][0]
    assert card["type"] == "workout_plan"
    label_text = " ".join(f["label"] for f in card["fields"])
    assert "advanced" in label_text.lower()


@pytest.mark.asyncio
async def test_workout_plan_actions(open_app):
    """workout_plan response has 'Start This Week' and 'Adjust Level' actions."""
    body = json.dumps({"message": {"content": "give me a workout routine"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    action_labels = [a["label"] for a in resp.json().get("actions", [])]
    assert "Start This Week" in action_labels
    assert "Adjust Level" in action_labels


# ---------------------------------------------------------------------------
# Intent: progress_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_check_happy_path(open_app):
    """A progress-related message returns a progress_check card."""
    body = json.dumps({"message": {"content": "how am i doing with my progress?"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    data = resp.json()
    _assert_success(data)
    _assert_card(data["cards"][0], "progress_check")
    assert data["cards"][0]["title"] == "Performance Snapshot"


@pytest.mark.asyncio
async def test_progress_check_card_fields(open_app):
    """progress_check card contains Running pace, Strength, Consistency, and Next target fields."""
    body = json.dumps({"message": {"content": "check my progress and results"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    card = resp.json()["cards"][0]
    labels = [f["label"] for f in card["fields"]]
    assert "Running pace" in labels
    assert "Strength" in labels
    assert "Consistency" in labels
    assert "Next target" in labels


@pytest.mark.asyncio
async def test_progress_check_actions(open_app):
    """progress_check response has 'Set Next Target' and 'Weekly Check-in' actions."""
    body = json.dumps({"message": {"content": "how am I improving? check my metrics"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    action_labels = [a["label"] for a in resp.json().get("actions", [])]
    assert "Set Next Target" in action_labels
    assert "Weekly Check-in" in action_labels


# ---------------------------------------------------------------------------
# Intent: nutrition_guidance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nutrition_guidance_happy_path(open_app):
    """A nutrition-related message returns a nutrition_guidance card."""
    body = json.dumps({"message": {"content": "what should I eat before workout?"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    data = resp.json()
    _assert_success(data)
    _assert_card(data["cards"][0], "nutrition_guidance")
    assert data["cards"][0]["title"] == "Workout Nutrition"


@pytest.mark.asyncio
async def test_nutrition_guidance_card_fields(open_app):
    """nutrition_guidance card contains hydration and daily baseline fields."""
    body = json.dumps({"message": {"content": "nutrition and diet advice for working out"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    card = resp.json()["cards"][0]
    labels = [f["label"] for f in card["fields"]]
    assert any("hydration" in lbl.lower() for lbl in labels)
    assert any("daily baseline" in lbl.lower() for lbl in labels)


@pytest.mark.asyncio
async def test_nutrition_guidance_actions(open_app):
    """nutrition_guidance response has 'Build Meal Plan' and 'Swap Options' actions."""
    body = json.dumps({"message": {"content": "I need a meal plan with protein and carbs"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    action_labels = [a["label"] for a in resp.json().get("actions", [])]
    assert "Build Meal Plan" in action_labels
    assert "Swap Options" in action_labels


# ---------------------------------------------------------------------------
# Fallback intent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_unknown_message_defaults_to_workout_plan(open_app):
    """An unrecognised message defaults to workout_plan intent."""
    body = json.dumps({"message": {"content": "hello there"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    data = resp.json()
    _assert_success(data)
    assert data["cards"][0]["type"] == "workout_plan"


# ---------------------------------------------------------------------------
# Malformed payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_message_content_returns_400(open_app):
    """A request with an empty message.content returns 400."""
    body = json.dumps({"message": {"content": ""}}).encode()

    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_missing_message_key_returns_400(open_app):
    """A request with no message key at all returns 400."""
    body = json.dumps({"profile": {"display_name": "Alice"}}).encode()

    async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
        resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Display name personalisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_name_appears_in_reply(open_app):
    """When profile.display_name is provided, the reply text greets the user by name."""
    body = json.dumps({
        "message": {"content": "I need a workout plan"},
        "profile": {"display_name": "Maria"},
    }).encode()

    with patch("litellm.acompletion", _mock_acompletion("Great plan ahead.")):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    data = resp.json()
    reply_text = " ".join(p["text"] for p in data["content_parts"] if p.get("type") == "text")
    assert "Maria" in reply_text


@pytest.mark.asyncio
async def test_no_profile_still_returns_200(open_app):
    """When profile is absent, the response is still 200 with a valid card."""
    body = json.dumps({"message": {"content": "strength training program"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    _assert_success(resp.json())


# ---------------------------------------------------------------------------
# Card metadata.capability_state == "live" for all intents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected_type", [
    ("I need a workout routine", "workout_plan"),
    ("check my progress and how I am doing", "progress_check"),
    ("what should I eat before workout?", "nutrition_guidance"),
])
async def test_card_metadata_capability_state_live(open_app, message, expected_type):
    """metadata.capability_state is 'live' for all card types."""
    body = json.dumps({"message": {"content": message}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    card = resp.json()["cards"][0]
    assert card["type"] == expected_type
    assert card.get("metadata", {}).get("capability_state") == "live"


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected_type", [
    ("I need a workout routine", "workout_plan"),
    ("check my progress and how I am doing", "progress_check"),
    ("what should I eat before workout?", "nutrition_guidance"),
])
async def test_card_badges_include_fitness_and_webhook(open_app, message, expected_type):
    """All card types include both 'Fitness' and 'Webhook' in their badges."""
    body = json.dumps({"message": {"content": message}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    card = resp.json()["cards"][0]
    assert "Fitness" in card["badges"]
    assert "Webhook" in card["badges"]


# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_signature_accepted(secret_app):
    """A correctly signed request is accepted (200)."""
    body = json.dumps({"message": {"content": "I need a training plan"}}).encode()
    headers = _signed_headers(body)

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers=headers)

    assert resp.status_code == 200
    _assert_success(resp.json())


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(secret_app):
    """A request with a wrong X-Signature header is rejected with 401."""
    body = json.dumps({"message": {"content": "I need a training plan"}}).encode()

    async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
        resp = await client.post(
            "/",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Timestamp": TEST_TIMESTAMP,
                "X-Signature": "sha256=deadbeefdeadbeefdeadbeef",
            },
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_signature_returns_401(secret_app):
    """When WEBHOOK_SECRET is set but X-Signature is absent, returns 401."""
    body = json.dumps({"message": {"content": "I need a training plan"}}).encode()

    async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
        resp = await client.post(
            "/",
            content=body,
            headers={"Content-Type": "application/json", "X-Timestamp": TEST_TIMESTAMP},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_timestamp_returns_401(secret_app):
    """When WEBHOOK_SECRET is set but X-Timestamp is absent, returns 401."""
    body = json.dumps({"message": {"content": "I need a training plan"}}).encode()
    sig = _make_signature(TEST_SECRET, TEST_TIMESTAMP, body)

    async with AsyncClient(transport=ASGITransport(app=secret_app), base_url="http://test") as client:
        resp = await client.post(
            "/",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": sig,
            },
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_signature_required_when_secret_unset(open_app):
    """When WEBHOOK_SECRET is not set, unsigned requests are accepted."""
    body = json.dumps({"message": {"content": "give me a workout program"}}).encode()

    with patch("litellm.acompletion", _mock_acompletion()):
        async with AsyncClient(transport=ASGITransport(app=open_app), base_url="http://test") as client:
            resp = await client.post("/", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    _assert_success(resp.json())
