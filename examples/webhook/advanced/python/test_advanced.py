"""
Tests for the advanced connector-style webhook server.

Demonstrates:
- Connector action routing (order_status, schedule_appointment)
- Failure/retry behavior with retry_after and retry_suggestion content_json
- Idempotency: same action_id returns cached result from the action log
- Main webhook routing based on context.intent
- Unknown action returns 404
- HMAC signature validation
- Empty body handling

Run with:
    pytest test_advanced.py
"""

import hashlib
import hmac
import json
import unittest.mock

import pytest
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signature(body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest matching the server's expected format."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def open_app(monkeypatch):
    """Return the FastAPI app with WEBHOOK_SECRET unset (dev mode)."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    import importlib
    import server as srv

    importlib.reload(srv)
    # Clear the action log between tests
    srv.action_log.clear()
    return srv.app


@pytest.fixture
def secret_app(monkeypatch):
    """Return the FastAPI app with WEBHOOK_SECRET=testsecret set."""
    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    import importlib
    import server as srv

    importlib.reload(srv)
    srv.action_log.clear()
    return srv.app


# ---------------------------------------------------------------------------
# Connector action endpoint tests - order_status
# ---------------------------------------------------------------------------


async def test_order_status_returns_tracking_data(open_app):
    """POST /actions/order_status returns mock tracking info."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/actions/order_status",
            json={"action_id": "act-001", "order_id": "ORD-12345"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "order_id" in data
    assert "status" in data
    assert "tracking" in data


async def test_order_status_includes_action_id_in_response(open_app):
    """The order_status response echoes back the action_id."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/actions/order_status",
            json={"action_id": "act-xyz", "order_id": "ORD-99"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["action_id"] == "act-xyz"


# ---------------------------------------------------------------------------
# Connector action endpoint tests - schedule_appointment
# ---------------------------------------------------------------------------


async def test_schedule_appointment_success_path(open_app):
    """When scheduling succeeds, response includes confirmation details."""
    import server as srv

    # Force success by patching the random failure simulation
    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=False):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/actions/schedule_appointment",
                json={
                    "action_id": "act-sched-001",
                    "date": "2025-06-15",
                    "time": "14:00",
                    "service": "consultation",
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "confirmation_id" in data
    assert "scheduled_at" in data


async def test_schedule_appointment_failure_path(open_app):
    """When scheduling fails (simulated), response includes retry_after."""
    import server as srv

    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/actions/schedule_appointment",
                json={
                    "action_id": "act-sched-fail",
                    "date": "2025-06-15",
                    "time": "14:00",
                    "service": "consultation",
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "retry_after" in data
    assert isinstance(data["retry_after"], int)
    assert data["retry_after"] > 0


# ---------------------------------------------------------------------------
# Unknown action returns 404
# ---------------------------------------------------------------------------


async def test_unknown_action_returns_404(open_app):
    """Posting to an unrecognised action type returns HTTP 404."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/actions/nonexistent_action",
            json={"action_id": "act-x"},
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Main webhook routing based on context.intent
# ---------------------------------------------------------------------------


async def test_main_webhook_routes_to_order_status_action(open_app):
    """When context.intent is 'order_status', the main webhook triggers an action."""
    import server as srv

    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=False):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={
                    "message": {"content": "Where is my order?"},
                    "context": {
                        "intent": "order_status",
                        "action_id": "act-wh-001",
                        "order_id": "ORD-55555",
                    },
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "content_json" in data
    # The reply should acknowledge the order status
    assert data["content_json"] is not None
    assert data["content_json"].get("type") == "action_result"


async def test_main_webhook_routes_to_schedule_appointment_action(open_app):
    """When context.intent is 'schedule_appointment', the webhook triggers scheduling."""
    import server as srv

    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=False):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={
                    "message": {"content": "Book me an appointment"},
                    "context": {
                        "intent": "schedule_appointment",
                        "action_id": "act-wh-sched-001",
                        "date": "2025-07-01",
                        "time": "10:00",
                        "service": "demo",
                    },
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["content_json"] is not None
    assert data["content_json"].get("type") == "action_result"


async def test_main_webhook_no_action_for_plain_message(open_app):
    """When context has no special intent, the main webhook returns a plain reply."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={"message": {"content": "Hello there"}},
        )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 0
    # No special content_json action result for plain messages
    cj = data.get("content_json")
    if cj is not None:
        assert cj.get("type") != "action_result"


# ---------------------------------------------------------------------------
# Retry behavior - retry_after included on failure
# ---------------------------------------------------------------------------


async def test_retry_after_present_in_webhook_response_on_failure(open_app):
    """When a connector action fails, the webhook reply includes retry_after."""
    import server as srv

    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                json={
                    "message": {"content": "Book me an appointment"},
                    "context": {
                        "intent": "schedule_appointment",
                        "action_id": "act-retry-test",
                        "date": "2025-07-01",
                        "time": "09:00",
                        "service": "demo",
                    },
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert "retry_after" in data
    assert isinstance(data["retry_after"], int)
    assert data["content_json"]["type"] == "retry_suggestion"


# ---------------------------------------------------------------------------
# Idempotency: same action_id returns cached result
# ---------------------------------------------------------------------------


async def test_idempotency_same_action_id_returns_cached_result(open_app):
    """Calling the same action_id twice returns the cached first result."""
    import server as srv

    # First call succeeds
    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=False):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response1 = await client.post(
                "/actions/schedule_appointment",
                json={
                    "action_id": "act-idem-001",
                    "date": "2025-08-01",
                    "time": "11:00",
                    "service": "followup",
                },
            )
    assert response1.status_code == 200
    data1 = response1.json()
    first_confirmation = data1.get("confirmation_id")

    # Second call with same action_id and failure simulation should still return the
    # cached successful result (idempotency wins over failure simulation)
    with unittest.mock.patch.object(srv, "_simulate_failure", return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=open_app), base_url="http://test"
        ) as client:
            response2 = await client.post(
                "/actions/schedule_appointment",
                json={
                    "action_id": "act-idem-001",
                    "date": "2025-08-01",
                    "time": "11:00",
                    "service": "followup",
                },
            )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2.get("confirmation_id") == first_confirmation
    # Cached result was success
    assert data2["success"] is True


async def test_idempotency_cached_flag_in_response(open_app):
    """When a cached result is returned, the response includes cached=True."""
    action_payload = {
        "action_id": "act-idem-cached",
        "order_id": "ORD-1111",
    }
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        await client.post("/actions/order_status", json=action_payload)
        response2 = await client.post("/actions/order_status", json=action_payload)

    assert response2.status_code == 200
    data2 = response2.json()
    assert data2.get("cached") is True


# ---------------------------------------------------------------------------
# HMAC signature validation
# ---------------------------------------------------------------------------


async def test_valid_signature_passes(secret_app):
    """A correctly signed request is accepted."""
    payload = json.dumps({"message": {"content": "hi"}}).encode()
    sig = _make_signature(payload, "testsecret")

    async with AsyncClient(
        transport=ASGITransport(app=secret_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=payload,
            headers={"Content-Type": "application/json", "X-Signature": sig},
        )
    assert response.status_code == 200


async def test_invalid_signature_returns_401(secret_app):
    """A request with a wrong signature is rejected with 401."""
    payload = json.dumps({"message": {"content": "hi"}}).encode()

    async with AsyncClient(
        transport=ASGITransport(app=secret_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=payload,
            headers={"Content-Type": "application/json", "X-Signature": "deadbeef"},
        )
    assert response.status_code == 401


async def test_missing_signature_with_secret_set_returns_401(secret_app):
    """When WEBHOOK_SECRET is set, a request without X-Signature is rejected."""
    payload = json.dumps({"message": {"content": "hi"}}).encode()

    async with AsyncClient(
        transport=ASGITransport(app=secret_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 401


async def test_no_signature_required_when_secret_unset(open_app):
    """When WEBHOOK_SECRET is not configured, any request is accepted."""
    payload = json.dumps({"message": {"content": "hi"}}).encode()

    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Empty body handling
# ---------------------------------------------------------------------------


async def test_empty_body_handled_gracefully(open_app):
    """An empty JSON body returns 200 without crashing."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post("/", json={})
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data


async def test_non_json_body_handled_gracefully(open_app):
    """A non-JSON body returns 200 without crashing (falls back to empty state)."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=b"not json at all",
            headers={"Content-Type": "text/plain"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
