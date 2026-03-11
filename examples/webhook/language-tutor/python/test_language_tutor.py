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


def test_intents():
    m = _m()
    assert m.detect_intent("Teach me how to order food in Italian") == "phrase_help"
    assert m.detect_intent("Give me a quick Spanish conversation quiz") == "quiz"
    assert m.detect_intent("Create a beginner lesson plan") == "lesson_plan"


@patch("app.call_llm")
def test_phrase_help_response(mock_call_llm):
    mock_call_llm.return_value = "Phrase support"
    c = _client()
    r = c.post("/", json=_payload("How do I introduce myself in Portuguese?"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "phrase_help"


@patch("app.call_llm")
def test_quiz_response(mock_call_llm):
    mock_call_llm.return_value = "Quiz ready"
    c = _client()
    r = c.post("/", json=_payload("Give me a quick Spanish conversation quiz"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "quiz"


@patch("app.call_llm")
def test_lesson_response(mock_call_llm):
    mock_call_llm.return_value = "Lesson plan ready"
    c = _client()
    r = c.post("/", json=_payload("Build a beginner Portuguese study plan"))
    assert r.status_code == 200
    assert r.json()["cards"][0]["type"] == "lesson_plan"


def test_empty_message_400():
    c = _client()
    assert c.post("/", json=_payload("")) .status_code == 400


@patch("app.WEBHOOK_SECRET", "secret")
def test_signature_gate_on():
    c = _client()
    body = json.dumps(_payload("teach me"))
    assert c.post("/", content=body, headers={"content-type": "application/json"}).status_code == 401


@patch("app.WEBHOOK_SECRET", "secret")
def test_signature_valid():
    c = _client()
    body = json.dumps(_payload("teach me"))
    ts = "1700000000"
    sig = _sign("secret", ts, body)
    r = c.post(
        "/",
        content=body,
        headers={"content-type": "application/json", "x-timestamp": ts, "x-signature": sig},
    )
    assert r.status_code == 200
