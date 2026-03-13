"""
Tests for the Travel Planner webhook server.

Covers:
- Health and root endpoints
- Intent detection unit tests
- Itinerary intent happy path (destination extraction for "Barcelona")
- Flight compare intent happy path (flight option fields)
- Booking handoff intent (capability_state == requires_connector, badges)
- Fallback intent (no keywords → itinerary)
- Malformed payload (empty content → 400)
- HMAC signature verification (valid, invalid, missing timestamp/signature)

Run with:
    cd /Users/markmacmahon/dev/luzia-nexo-api
    uv run pytest examples/webhook/travel-planner/python/test_travel_planner.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Isolated module import — avoids collision when pytest runs multiple webhook
# test files in the same process (each has its own app.py).
# ---------------------------------------------------------------------------
_APP_DIR = Path(__file__).resolve().parent
_MODULE_NAME = "travel_planner_app"


def _load_travel_app():
    """Load (or reload) the travel-planner app.py with full isolation."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _APP_DIR / "app.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


travel_app = _load_travel_app()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "2026-03"
_TIMESTAMP = "1700000000"
_SECRET = "secret"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(content: str) -> dict:
    return {
        "event": "message_created",
        "app": {},
        "thread": {},
        "message": {"role": "user", "content": content},
    }


def _sign(secret: str, timestamp: str, body: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "sha256=" + digest


def _card(data: dict) -> dict:
    cards = data.get("cards", [])
    assert cards, f"Expected at least one card in response, got: {data}"
    return cards[0]


def _mock_llm_response(text: str = "Travel plan ready.") -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = text
    return mock_resp


# ---------------------------------------------------------------------------
# Sync tests (existing coverage using TestClient)
# ---------------------------------------------------------------------------


def test_root_health():
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    assert c.get("/").status_code == 200
    assert c.get("/health").json()["status"] == "ok"


def test_root_returns_capabilities():
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    data = c.get("/").json()
    intent_names = [cap["intent"] for cap in data.get("capabilities", [])]
    assert "itinerary" in intent_names
    assert "flight_compare" in intent_names
    assert "booking_handoff" in intent_names
    assert data["showcase"]["superseded_by"] == "travel-planning"


def test_agent_card_endpoint():
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    resp = c.get("/.well-known/agent.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capabilities"]["items"][0]["name"] == "travel.planner"
    assert data["capabilities"]["items"][0]["metadata"]["showcase_role"] == "secondary"
    assert data["capabilities"]["items"][0]["metadata"]["superseded_by"] == "travel-planning"


def test_intent_mapping():
    assert travel_app.detect_intent("Plan a romantic weekend in Barcelona") == "itinerary"
    assert travel_app.detect_intent("Compare flights to Lisbon") == "flight_compare"
    assert travel_app.detect_intent("Book this option now") == "booking_handoff"


def test_intent_fallback_returns_itinerary():
    assert travel_app.detect_intent("What's the weather like?") == "itinerary"
    assert travel_app.detect_intent("Tell me something interesting") == "itinerary"


def test_destination_extraction():
    assert travel_app._extract_destination("Plan a trip to Barcelona") == "Barcelona"
    assert travel_app._extract_destination("Flights to Tokyo next week") == "Tokyo"
    assert travel_app._extract_destination("Weekend in Lisbon") == "Lisbon"
    assert travel_app._extract_destination("No city mentioned") == "Barcelona"


@patch("travel_planner_app.call_llm")
def test_itinerary_response(mock_call_llm):
    mock_call_llm.return_value = "Trip draft ready"
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    r = c.post("/", json=_payload("I have 3 days in Tokyo"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "itinerary"


@patch("travel_planner_app.call_llm")
def test_flight_response(mock_call_llm):
    mock_call_llm.return_value = "Compared options"
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    r = c.post("/", json=_payload("Compare flights to Lisbon next month"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "flight_compare"


@patch("travel_planner_app.call_llm")
def test_booking_handoff_response(mock_call_llm):
    mock_call_llm.return_value = "Handoff prepared"
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    r = c.post("/", json=_payload("Please book this plan"))
    assert r.status_code == 200
    data = r.json()
    assert data["cards"][0]["type"] == "booking_handoff"
    assert data["cards"][0]["metadata"]["capability_state"] == "requires_connector"


def test_empty_message_400():
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    assert c.post("/", json=_payload("")).status_code == 400


@patch("travel_planner_app.WEBHOOK_SECRET", "secret")
def test_signature_gate_on():
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    body = json.dumps(_payload("plan"))
    assert c.post("/", content=body, headers={"content-type": "application/json"}).status_code == 401


@patch("travel_planner_app.WEBHOOK_SECRET", "secret")
def test_signature_valid():
    c = TestClient(travel_app.app, raise_server_exceptions=False)
    body = json.dumps(_payload("plan"))
    ts = _TIMESTAMP
    sig = _sign("secret", ts, body)
    r = c.post(
        "/",
        content=body,
        headers={"content-type": "application/json", "x-timestamp": ts, "x-signature": sig},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Async tests using AsyncClient + ASGITransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_itinerary_intent_happy_path():
    """Itinerary intent: Barcelona in message triggers itinerary card."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Here is your itinerary.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=_payload("What's a good itinerary for Barcelona?"))

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["status"] == "completed"
    assert data["task"]["status"] == "completed"
    assert data["capability"]["name"] == "travel.planner"
    assert isinstance(data["artifacts"], list)
    assert isinstance(data.get("content_parts"), list)
    assert len(data["content_parts"]) > 0

    card = _card(data)
    assert card["type"] == "itinerary"
    assert "Barcelona" in card["title"]
    assert "Travel" in card["badges"]
    assert "Webhook" in card["badges"]
    assert card["metadata"]["capability_state"] == "live"


@pytest.mark.asyncio
async def test_async_itinerary_destination_extraction():
    """Destination 'Barcelona' is extracted from message and reflected in card title."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Barcelona itinerary ready.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=_payload("Plan a trip to Barcelona for 3 days"))

    assert response.status_code == 200
    card = _card(response.json())
    assert card["type"] == "itinerary"
    assert "Barcelona" in card["title"]


@pytest.mark.asyncio
async def test_async_itinerary_day_fields_present():
    """Itinerary card fields include Day 1, Day 2, Day 3, and Budget."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Ready.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=_payload("Plan my Barcelona trip"))

    card = _card(response.json())
    field_labels = [f["label"] for f in card["fields"]]
    assert "Day 1" in field_labels
    assert "Day 2" in field_labels
    assert "Day 3" in field_labels
    assert "Budget" in field_labels


@pytest.mark.asyncio
async def test_async_itinerary_actions():
    """Itinerary response includes adjust_plan and show_budget actions."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Ready.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=_payload("Plan a weekend in Barcelona"))

    data = response.json()
    action_ids = [a["id"] for a in data.get("actions", [])]
    assert "adjust_plan" in action_ids
    assert "show_budget" in action_ids


@pytest.mark.asyncio
async def test_async_flight_compare_intent_happy_path():
    """Flight compare intent: card has type flight_compare with option fields."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Here are your flight options.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", json=_payload("Compare flights to Barcelona, show cheapest price")
            )

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["status"] == "completed"

    card = _card(data)
    assert card["type"] == "flight_compare"
    assert card["title"] == "Flight Options"
    assert "Travel" in card["badges"]
    assert "Webhook" in card["badges"]
    assert card["metadata"]["capability_state"] == "live"

    field_labels = [f["label"] for f in card["fields"]]
    assert "Option A" in field_labels
    assert "Option B" in field_labels
    assert "Option C" in field_labels

    for field in card["fields"]:
        assert "EUR" in field["value"], f"Expected EUR in field value: {field['value']}"


@pytest.mark.asyncio
async def test_async_flight_compare_actions():
    """Flight compare response includes pick_option and set_price_watch actions."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Options ready.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", json=_payload("What are the cheapest flights to Lisbon?")
            )

    data = response.json()
    action_ids = [a["id"] for a in data.get("actions", [])]
    assert "pick_option" in action_ids
    assert "set_price_watch" in action_ids


@pytest.mark.asyncio
async def test_async_booking_handoff_intent_happy_path():
    """Booking handoff: capability_state is requires_connector and badge present."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Booking handoff ready.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", json=_payload("Book a hotel in Barcelona and confirm booking")
            )

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["status"] == "completed"

    card = _card(data)
    assert card["type"] == "booking_handoff"
    assert card["metadata"]["capability_state"] == "requires_connector"
    assert "Requires Connector" in card["badges"]
    assert "Travel" in card["badges"]


@pytest.mark.asyncio
async def test_async_booking_handoff_actions():
    """Booking handoff response includes approve_handoff and change_constraints actions."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Ready.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", json=_payload("Reserve a hotel, checkout, confirm booking")
            )

    data = response.json()
    action_ids = [a["id"] for a in data.get("actions", [])]
    assert "approve_handoff" in action_ids
    assert "change_constraints" in action_ids


@pytest.mark.asyncio
async def test_async_fallback_intent_returns_itinerary():
    """Messages with no recognized keywords fall back to itinerary intent."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Default response.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", json=_payload("What do you think about the weather today?")
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    card = _card(data)
    assert card["type"] == "itinerary"


@pytest.mark.asyncio
async def test_async_fallback_uses_default_destination_barcelona():
    """Fallback with no known city defaults destination to Barcelona."""
    with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Default response.")):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", json=_payload("Tell me something interesting")
            )

    card = _card(response.json())
    assert "Barcelona" in card["title"]


@pytest.mark.asyncio
async def test_async_empty_message_returns_400():
    """Empty message content is rejected with HTTP 400."""
    async with AsyncClient(
        transport=ASGITransport(app=travel_app.app), base_url="http://test"
    ) as client:
        response = await client.post("/", json=_payload(""))

    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_async_missing_message_returns_400():
    """Payload missing the 'message' key is rejected with HTTP 400."""
    async with AsyncClient(
        transport=ASGITransport(app=travel_app.app), base_url="http://test"
    ) as client:
        response = await client.post("/", json={"profile": {"name": "Ghost"}})

    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_async_valid_hmac_signature_accepted():
    """A correctly signed request is accepted when WEBHOOK_SECRET is set."""
    body_str = json.dumps(_payload("Plan a trip to Barcelona"))
    body_bytes = body_str.encode("utf-8")
    sig = _sign(_SECRET, _TIMESTAMP, body_str)

    with patch("travel_planner_app.WEBHOOK_SECRET", _SECRET):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            with patch("travel_planner_app.call_llm", new=AsyncMock(return_value="Signed response.")):
                response = await client.post(
                    "/",
                    content=body_bytes,
                    headers={
                        "content-type": "application/json",
                        "x-timestamp": _TIMESTAMP,
                        "x-signature": sig,
                    },
                )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_async_invalid_hmac_signature_rejected():
    """A request with a wrong signature is rejected with HTTP 401."""
    body_str = json.dumps(_payload("Plan a trip"))
    body_bytes = body_str.encode("utf-8")

    with patch("travel_planner_app.WEBHOOK_SECRET", _SECRET):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=body_bytes,
                headers={
                    "content-type": "application/json",
                    "x-timestamp": _TIMESTAMP,
                    "x-signature": "sha256=deadbeef",
                },
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_async_missing_signature_header_rejected():
    """When WEBHOOK_SECRET is set, a request without X-Signature is rejected."""
    body_str = json.dumps(_payload("Plan a trip"))
    body_bytes = body_str.encode("utf-8")

    with patch("travel_planner_app.WEBHOOK_SECRET", _SECRET):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=body_bytes,
                headers={"content-type": "application/json", "x-timestamp": _TIMESTAMP},
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_async_missing_timestamp_header_rejected():
    """When WEBHOOK_SECRET is set, a request without X-Timestamp is rejected."""
    body_str = json.dumps(_payload("Plan a trip"))
    body_bytes = body_str.encode("utf-8")
    sig = _sign(_SECRET, _TIMESTAMP, body_str)

    with patch("travel_planner_app.WEBHOOK_SECRET", _SECRET):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=body_bytes,
                headers={"content-type": "application/json", "x-signature": sig},
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_async_no_signature_required_when_secret_unset():
    """When WEBHOOK_SECRET is empty/unset, unsigned requests are accepted."""
    with patch("travel_planner_app.WEBHOOK_SECRET", ""), patch(
        "travel_planner_app.call_llm", new=AsyncMock(return_value="Open response.")
    ):
        async with AsyncClient(
            transport=ASGITransport(app=travel_app.app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=_payload("Plan a trip"))

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
