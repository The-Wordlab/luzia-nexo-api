from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ingest_and_list_events() -> None:
    demo_key = "demo_abc"
    ingest = client.post(
        f"/v1/ingest/{demo_key}",
        json={"event": "message_received", "content": "hello"},
    )
    assert ingest.status_code == 200
    assert ingest.json()["status"] == "accepted"

    events = client.get(f"/v1/events/{demo_key}?limit=10")
    assert events.status_code == 200
    body = events.json()
    assert body["demo_key"] == demo_key
    assert body["count"] >= 1


def test_invalid_demo_key_rejected() -> None:
    resp = client.post("/v1/ingest/bad key", json={"x": 1})
    assert resp.status_code == 400


def test_redacts_sensitive_fields() -> None:
    demo_key = "demo_redact"
    client.post(
        f"/v1/ingest/{demo_key}",
        json={
            "Authorization": "Bearer abc",
            "webhook_secret": "super-secret",
            "normal": "ok",
        },
    )
    events = client.get(f"/v1/events/{demo_key}")
    payload = events.json()["events"][0]["payload"]
    assert payload["Authorization"] == "[REDACTED]"
    assert payload["webhook_secret"] == "[REDACTED]"
    assert payload["normal"] == "ok"
