import hashlib
import hmac

from fastapi.testclient import TestClient

from server import app, build_reply


client = TestClient(app)


def test_build_reply() -> None:
    assert build_reply("hello") == "Echo: hello"
    assert build_reply("") == "Echo:"
    assert (
        build_reply(
            "book a table",
            display_name="Ava",
            locale="en",
            dietary_preferences="vegetarian",
        )
        == "Ava, you said: book a table (locale=en, dietary=vegetarian)"
    )


def test_webhook_echo() -> None:
    resp = client.post("/webhook", json={"message": {"content": "hi"}})
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Echo: hi"}


def test_webhook_profile_context() -> None:
    resp = client.post(
        "/webhook",
        json={
            "message": {"content": "recommend dinner"},
            "profile": {
                "display_name": "Mia",
                "locale": "en",
                "dietary_preferences": "vegan",
                "future_field": "ignored",
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "Mia, you said: recommend dinner (locale=en, dietary=vegan)"
    }


def _sign(secret: str, timestamp: str, body: str) -> str:
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def test_webhook_with_valid_signature(monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    body = '{"message":{"content":"hi"}}'
    ts = "1700000000"
    sig = _sign("test-secret", ts, body)
    resp = client.post("/webhook", data=body, headers={"X-Timestamp": ts, "X-Signature": sig})
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Echo: hi"}


def test_webhook_with_invalid_signature(monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    body = '{"message":{"content":"hi"}}'
    resp = client.post(
        "/webhook",
        data=body,
        headers={"X-Timestamp": "1700000000", "X-Signature": "sha256=invalid"},
    )
    assert resp.status_code == 401
