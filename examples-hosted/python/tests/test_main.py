from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
SECRET = {"X-App-Secret": "test-secret"}


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
    assert info_resp.json()["repository_url"] == "https://github.com/The-Wordlab/luzia-nexo-api"
    assert info_resp.json()["partner_portal_url"] == "https://nexo.luzia.com/partners"
    assert info_resp.json()["api_secret_help"]["contact_email"] == "mmm@luzia.com"
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
    assert resp.json()["reply"] == "Echo: hi"


def test_webhook_advanced_order_status(monkeypatch) -> None:
    monkeypatch.setenv("EXAMPLES_SHARED_API_SECRET", "test-secret")
    resp = client.post(
        "/webhook/advanced",
        json={"context": {"intent": "order_status", "order_id": "ORD-1"}},
        headers=SECRET,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_json"]["order_id"] == "ORD-1"
