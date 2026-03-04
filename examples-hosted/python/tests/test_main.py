from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
SECRET = {"X-App-Secret": "test-secret"}


def _response_text(body: dict) -> str:
    parts = body.get("content_parts") or []
    return " ".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    )


def test_health_is_public() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_info_endpoints_are_public() -> None:
    root_resp = client.get("/")
    info_resp = client.get("/info")
    assert root_resp.status_code == 200
    assert info_resp.status_code == 200
    assert "text/html" in root_resp.headers["content-type"]
    assert "text/html" in info_resp.headers["content-type"]


def test_info_endpoints_support_json() -> None:
    root_resp = client.get("/?format=json")
    info_resp = client.get("/info", headers={"Accept": "application/json"})
    assert root_resp.status_code == 200
    assert info_resp.status_code == 200
    assert root_resp.json()["service"] == "nexo-examples-py"
    assert info_resp.json()["docs_url"] == "https://the-wordlab.github.io/luzia-nexo-api/"
    assert any(e["path"] == "/webhook/minimal" for e in info_resp.json()["endpoints"])


def test_webhook_requires_secret(monkeypatch) -> None:
    monkeypatch.setenv("EXAMPLES_SHARED_API_SECRET", "test-secret")
    resp = client.post("/webhook/minimal", json={"message": {"content": "hi"}})
    assert resp.status_code == 401


def test_webhook_minimal_with_secret(monkeypatch) -> None:
    monkeypatch.setenv("EXAMPLES_SHARED_API_SECRET", "test-secret")
    resp = client.post(
        "/webhook/minimal",
        json={"message": {"content": "hi"}},
        headers=SECRET,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == "2026-03-01"
    assert body["status"] == "success"
    assert _response_text(body) == "Echo: hi"


def test_webhook_minimal_profile_context(monkeypatch) -> None:
    monkeypatch.setenv("EXAMPLES_SHARED_API_SECRET", "test-secret")
    resp = client.post(
        "/webhook/minimal",
        json={
            "message": {"content": "recommend dinner"},
            "profile": {
                "display_name": "Mia",
                "locale": "en",
                "dietary_preferences": "vegan",
                "future_field": "ignored",
            },
        },
        headers=SECRET,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert _response_text(body) == "Mia, you said: recommend dinner (locale=en, dietary=vegan)"


def test_webhook_advanced_order_status(monkeypatch) -> None:
    monkeypatch.setenv("EXAMPLES_SHARED_API_SECRET", "test-secret")
    resp = client.post(
        "/webhook/advanced",
        json={"context": {"intent": "order_status", "order_id": "ORD-1"}},
        headers=SECRET,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cards"][0]["order_id"] == "ORD-1"
