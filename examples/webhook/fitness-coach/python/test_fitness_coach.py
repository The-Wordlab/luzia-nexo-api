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
    m = _m()
    return TestClient(m.app, raise_server_exceptions=False)


def _sign(secret: str, timestamp: str, body: str) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _payload(content: str):
    return {
        "event": "message_created",
        "app": {},
        "thread": {},
        "message": {"role": "user", "content": content},
    }


def test_root_and_health():
    c = _client()
    assert c.get("/").status_code == 200
    assert c.get("/health").json()["status"] == "ok"


def test_detect_intents():
    m = _m()
    assert m.detect_intent("Design a 4-week workout plan") == "workout_plan"
    assert m.detect_intent("How am I doing this month?") == "progress_check"
    assert m.detect_intent("What should I eat before workout?") == "nutrition_guidance"


@patch("app.call_llm")
def test_workout_plan_response(mock_call_llm):
    mock_call_llm.return_value = "Plan ready"
    c = _client()
    r = c.post("/", json=_payload("Create a beginner workout plan"))
    assert r.status_code == 200
    data = r.json()
    assert data["schema_version"] == "2026-03-01"
    assert data["cards"][0]["type"] == "workout_plan"


@patch("app.call_llm")
def test_progress_response(mock_call_llm):
    mock_call_llm.return_value = "Progress looks good"
    c = _client()
    r = c.post("/", json=_payload("I ran 5k in 28 minutes, progress check"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "progress_check"


@patch("app.call_llm")
def test_nutrition_response(mock_call_llm):
    mock_call_llm.return_value = "Fueling guidance"
    c = _client()
    r = c.post("/", json=_payload("what should i eat after workout"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "nutrition_guidance"


def test_empty_message_400():
    c = _client()
    r = c.post("/", json=_payload(""))
    assert r.status_code == 400


@patch("app.WEBHOOK_SECRET", "secret")
def test_signature_required_when_secret_set():
    c = _client()
    body = json.dumps(_payload("workout plan"))
    assert c.post("/", content=body, headers={"content-type": "application/json"}).status_code == 401


@patch("app.WEBHOOK_SECRET", "secret")
def test_signature_valid_when_secret_set():
    c = _client()
    body = json.dumps(_payload("workout plan"))
    ts = "1700000000"
    sig = _sign("secret", ts, body)
    r = c.post(
        "/",
        content=body,
        headers={"content-type": "application/json", "x-timestamp": ts, "x-signature": sig},
    )
    assert r.status_code == 200
