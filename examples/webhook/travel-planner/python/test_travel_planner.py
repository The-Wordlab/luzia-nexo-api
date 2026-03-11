from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

_app = None


def _m():
    global _app
    if _app is None:
        import app as module

        _app = module
    return _app


def _client() -> TestClient:
    return TestClient(_m().app, raise_server_exceptions=False)


def _payload(content: str):
    return {
        "event": "message_created",
        "app": {},
        "thread": {},
        "message": {"role": "user", "content": content},
    }


def _sign(secret: str, timestamp: str, body: str) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def test_root_health():
    c = _client()
    assert c.get("/").status_code == 200
    assert c.get("/health").json()["status"] == "ok"


def test_intent_mapping():
    m = _m()
    assert m.detect_intent("Plan a romantic weekend in Barcelona") == "itinerary"
    assert m.detect_intent("Compare flights to Lisbon") == "flight_compare"
    assert m.detect_intent("Book this option now") == "booking_handoff"


@patch("app.call_llm")
def test_itinerary_response(mock_call_llm):
    mock_call_llm.return_value = "Trip draft ready"
    c = _client()
    r = c.post("/", json=_payload("I have 3 days in Tokyo"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "itinerary"


@patch("app.call_llm")
def test_flight_response(mock_call_llm):
    mock_call_llm.return_value = "Compared options"
    c = _client()
    r = c.post("/", json=_payload("Compare flights to Lisbon next month"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "flight_compare"


@patch("app.call_llm")
def test_booking_handoff_response(mock_call_llm):
    mock_call_llm.return_value = "Handoff prepared"
    c = _client()
    r = c.post("/", json=_payload("Please book this plan"))
    assert r.status_code == 200
    data = r.json()
    assert data["cards"][0]["type"] == "booking_handoff"
    assert data["cards"][0]["metadata"]["capability_state"] == "requires_connector"


def test_empty_message_400():
    c = _client()
    assert c.post("/", json=_payload("")).status_code == 400


@patch("app.WEBHOOK_SECRET", "secret")
def test_signature_gate_on():
    c = _client()
    body = json.dumps(_payload("plan"))
    assert c.post("/", content=body, headers={"content-type": "application/json"}).status_code == 401


@patch("app.WEBHOOK_SECRET", "secret")
def test_signature_valid():
    c = _client()
    body = json.dumps(_payload("plan"))
    ts = "1700000000"
    sig = _sign("secret", ts, body)
    r = c.post(
        "/",
        content=body,
        headers={"content-type": "application/json", "x-timestamp": ts, "x-signature": sig},
    )
    assert r.status_code == 200
