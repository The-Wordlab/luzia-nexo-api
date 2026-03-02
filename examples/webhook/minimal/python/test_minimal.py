import hashlib
import hmac

from fastapi.testclient import TestClient

from server import app, build_reply


client = TestClient(app)


def test_build_reply() -> None:
    assert build_reply("hello") == "Echo: hello"
    assert build_reply("") == "Echo:"


def test_webhook_echo() -> None:
    resp = client.post("/webhook", json={"message": {"content": "hi"}})
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Echo: hi"}


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
