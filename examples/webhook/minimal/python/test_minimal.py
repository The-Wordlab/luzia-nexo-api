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
