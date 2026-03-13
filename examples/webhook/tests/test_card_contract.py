"""Contract tests verifying card format compatibility with the dashboard frontend.

Tests all 9 intents (3 per app) against the PartnerCard interface:

    interface PartnerCard {
      type?: string;
      title?: string;
      subtitle?: string;
      badges?: string[];
      fields?: Array<{ label: string; value: string }>;
      metadata?: Record<string, unknown>;
    }

Response envelope contract:
    schema_version: "2026-03"
    status: "completed"
    content_parts: [{type: "text", text: "..."}]
    cards: [PartnerCard]
    actions: [{label: str, type: "primary"|"secondary"}]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# sys.path manipulation so we can import each app module directly
# ---------------------------------------------------------------------------
WEBHOOK_BASE = Path(__file__).parent.parent

FITNESS_COACH_PATH = WEBHOOK_BASE / "fitness-coach" / "python"
TRAVEL_PLANNER_PATH = WEBHOOK_BASE / "travel-planner" / "python"
LANGUAGE_TUTOR_PATH = WEBHOOK_BASE / "language-tutor" / "python"

for _path in (FITNESS_COACH_PATH, TRAVEL_PLANNER_PATH, LANGUAGE_TUTOR_PATH):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Import after path manipulation. Each module is named "app" so we import
# them under aliases to avoid collisions.
import importlib.util

def _load_app_module(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


fitness_app = _load_app_module(FITNESS_COACH_PATH, "fitness_app")
travel_app = _load_app_module(TRAVEL_PLANNER_PATH, "travel_app")
language_app = _load_app_module(LANGUAGE_TUTOR_PATH, "language_app")

# ---------------------------------------------------------------------------
# Fake LLM response so tests don't hit real APIs
# ---------------------------------------------------------------------------
FAKE_LLM_TEXT = "Here is a structured recommendation."

_fake_completion = AsyncMock(return_value=type(
    "R",
    (),
    {
        "choices": [
            type("C", (), {"message": type("M", (), {"content": FAKE_LLM_TEXT})()})()
        ]
    },
)())


# ---------------------------------------------------------------------------
# Helper to post to any FastAPI app and get the JSON response
# ---------------------------------------------------------------------------
async def _post_webhook(app_module, message_content: str) -> dict[str, Any]:
    payload = {"message": {"content": message_content}}
    async with AsyncClient(
        transport=ASGITransport(app=app_module.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 200, f"Unexpected status: {response.status_code} {response.text}"
    return response.json()


# ---------------------------------------------------------------------------
# Test matrix: (app_module, trigger_message, expected_intent)
# ---------------------------------------------------------------------------
INTENT_CASES = [
    # Fitness coach
    pytest.param(
        fitness_app,
        "I want a beginner workout plan for this week",
        "workout_plan",
        id="fitness-workout_plan",
    ),
    pytest.param(
        fitness_app,
        "How is my progress? I ran a 5km today",
        "progress_check",
        id="fitness-progress_check",
    ),
    pytest.param(
        fitness_app,
        "What should I eat before and after my workout?",
        "nutrition_guidance",
        id="fitness-nutrition_guidance",
    ),
    # Travel planner
    pytest.param(
        travel_app,
        "Can you create a 3 day itinerary for Barcelona?",
        "itinerary",
        id="travel-itinerary",
    ),
    pytest.param(
        travel_app,
        "Compare flights to Paris, what is the cheapest price?",
        "flight_compare",
        id="travel-flight_compare",
    ),
    pytest.param(
        travel_app,
        "Book and reserve a hotel, I want to confirm the booking handoff",
        "booking_handoff",
        id="travel-booking_handoff",
    ),
    # Language tutor
    pytest.param(
        language_app,
        "Can you quiz me on Spanish? Test me with a quick quiz",
        "quiz",
        id="language-quiz",
    ),
    pytest.param(
        language_app,
        "How do I say 'order food' in Italian? Teach me the phrase",
        "phrase_help",
        id="language-phrase_help",
    ),
    pytest.param(
        language_app,
        "I want to learn Spanish. Give me a weekly lesson plan to study",
        "lesson_plan",
        id="language-lesson_plan",
    ),
]


# ---------------------------------------------------------------------------
# Contract assertions
# ---------------------------------------------------------------------------

def _assert_card_contract(card: dict[str, Any], intent_label: str) -> None:
    """Assert a single card conforms to the PartnerCard interface."""
    assert isinstance(card, dict), f"[{intent_label}] card must be a dict"

    # type: str
    assert "type" in card, f"[{intent_label}] card missing 'type'"
    assert isinstance(card["type"], str), f"[{intent_label}] card.type must be str"

    # title: str
    assert "title" in card, f"[{intent_label}] card missing 'title'"
    assert isinstance(card["title"], str), f"[{intent_label}] card.title must be str"

    # subtitle: str
    assert "subtitle" in card, f"[{intent_label}] card missing 'subtitle'"
    assert isinstance(card["subtitle"], str), f"[{intent_label}] card.subtitle must be str"

    # badges: list[str]
    assert "badges" in card, f"[{intent_label}] card missing 'badges'"
    assert isinstance(card["badges"], list), f"[{intent_label}] card.badges must be a list"
    for badge in card["badges"]:
        assert isinstance(badge, str), f"[{intent_label}] each badge must be str, got {type(badge)}"

    # fields: list[{label: str, value: str}]
    assert "fields" in card, f"[{intent_label}] card missing 'fields'"
    assert isinstance(card["fields"], list), f"[{intent_label}] card.fields must be a list"
    for field in card["fields"]:
        assert isinstance(field, dict), f"[{intent_label}] each field must be a dict"
        assert "label" in field, f"[{intent_label}] field missing 'label'"
        assert "value" in field, f"[{intent_label}] field missing 'value'"
        assert isinstance(field["label"], str), f"[{intent_label}] field.label must be str"
        assert isinstance(field["value"], str), f"[{intent_label}] field.value must be str"

    # metadata.capability_state: one of ("live", "simulated", "requires_connector")
    assert "metadata" in card, f"[{intent_label}] card missing 'metadata'"
    metadata = card["metadata"]
    assert isinstance(metadata, dict), f"[{intent_label}] card.metadata must be a dict"
    assert "capability_state" in metadata, f"[{intent_label}] metadata missing 'capability_state'"
    valid_states = {"live", "simulated", "requires_connector"}
    assert metadata["capability_state"] in valid_states, (
        f"[{intent_label}] metadata.capability_state={metadata['capability_state']!r} "
        f"not in {valid_states}"
    )


def _assert_response_envelope(data: dict[str, Any], intent_label: str) -> None:
    """Assert the full response envelope contract."""
    # schema_version
    assert data.get("schema_version") == "2026-03", (
        f"[{intent_label}] schema_version must be '2026-03', got {data.get('schema_version')!r}"
    )

    # status
    assert "status" in data, f"[{intent_label}] response missing 'status'"
    assert data["status"] == "completed", (
        f"[{intent_label}] status must be 'completed', got {data['status']!r}"
    )

    # content_parts: list with at least one text part
    assert "content_parts" in data, f"[{intent_label}] response missing 'content_parts'"
    content_parts = data["content_parts"]
    assert isinstance(content_parts, list), f"[{intent_label}] content_parts must be a list"
    assert len(content_parts) >= 1, f"[{intent_label}] content_parts must have at least one part"
    text_parts = [p for p in content_parts if p.get("type") == "text"]
    assert len(text_parts) >= 1, f"[{intent_label}] content_parts must have at least one text part"
    for part in text_parts:
        assert isinstance(part.get("text"), str), f"[{intent_label}] text part must have 'text' str field"

    # cards
    assert "cards" in data, f"[{intent_label}] response missing 'cards'"
    cards = data["cards"]
    assert isinstance(cards, list), f"[{intent_label}] cards must be a list"
    assert len(cards) >= 1, f"[{intent_label}] cards must not be empty"
    for card in cards:
        _assert_card_contract(card, intent_label)

    # actions: [{label: str, type: "primary"|"secondary"}]
    assert "actions" in data, f"[{intent_label}] response missing 'actions'"
    actions = data["actions"]
    assert isinstance(actions, list), f"[{intent_label}] actions must be a list"
    for action in actions:
        assert isinstance(action, dict), f"[{intent_label}] each action must be a dict"
        assert "label" in action, f"[{intent_label}] action missing 'label'"
        assert isinstance(action["label"], str), f"[{intent_label}] action.label must be str"
        assert "type" in action, f"[{intent_label}] action missing 'type'"
        assert action["type"] in ("primary", "secondary"), (
            f"[{intent_label}] action.type must be 'primary' or 'secondary', got {action['type']!r}"
        )

    # Full response JSON under 64KB
    raw = json.dumps(data)
    assert len(raw.encode("utf-8")) < 64 * 1024, (
        f"[{intent_label}] response JSON exceeds 64KB ({len(raw.encode('utf-8'))} bytes)"
    )


# ---------------------------------------------------------------------------
# Parametrized contract test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("app_module,message,expected_intent", INTENT_CASES)
async def test_card_contract(app_module, message: str, expected_intent: str):
    """Each intent response must satisfy the full card format contract."""
    with patch("litellm.acompletion", new=AsyncMock(return_value=type(
        "R",
        (),
        {
            "choices": [
                type("C", (), {
                    "message": type("M", (), {"content": FAKE_LLM_TEXT})(),
                    "delta": type("D", (), {"content": ""})(),
                })()
            ]
        },
    )())):
        data = await _post_webhook(app_module, message)

    intent_label = f"{app_module.__name__}:{expected_intent}"
    _assert_response_envelope(data, intent_label)


# ---------------------------------------------------------------------------
# Direct card builder tests (pure sync, no LLM/HTTP needed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
def test_fitness_workout_plan_card_structure(level: str):
    card = fitness_app.build_workout_plan_card(level)
    _assert_card_contract(card, f"fitness_workout_plan:{level}")


def test_fitness_progress_card_structure():
    card = fitness_app.build_progress_card()
    _assert_card_contract(card, "fitness_progress_check")


def test_fitness_nutrition_card_structure():
    card = fitness_app.build_nutrition_card()
    _assert_card_contract(card, "fitness_nutrition_guidance")


@pytest.mark.parametrize("destination", ["Barcelona", "Tokyo", "Lisbon"])
def test_travel_itinerary_card_structure(destination: str):
    card = travel_app.build_itinerary_card(destination, 3)
    _assert_card_contract(card, f"travel_itinerary:{destination}")


@pytest.mark.parametrize("destination", ["Barcelona", "Paris"])
def test_travel_flights_card_structure(destination: str):
    card = travel_app.build_flights_card(destination)
    _assert_card_contract(card, f"travel_flight_compare:{destination}")


@pytest.mark.parametrize("destination", ["Barcelona", "Tokyo"])
def test_travel_booking_card_structure(destination: str):
    card = travel_app.build_booking_card(destination)
    _assert_card_contract(card, f"travel_booking_handoff:{destination}")


@pytest.mark.parametrize("language", ["Italian", "Spanish", "Portuguese"])
def test_language_phrase_card_structure(language: str):
    card = language_app.build_phrase_card(language)
    _assert_card_contract(card, f"language_phrase_help:{language}")


@pytest.mark.parametrize("language", ["Italian", "Spanish", "Portuguese"])
def test_language_quiz_card_structure(language: str):
    card = language_app.build_quiz_card(language)
    _assert_card_contract(card, f"language_quiz:{language}")


@pytest.mark.parametrize("language", ["Italian", "Spanish", "Portuguese"])
def test_language_lesson_card_structure(language: str):
    card = language_app.build_lesson_card(language)
    _assert_card_contract(card, f"language_lesson_plan:{language}")
