"""
Tests for the intermediate webhook server.

Demonstrates:
- Personalized replies using profile.name
- Locale-aware greetings (Spanish when profile.locale="es")
- content_json card hints based on context
- Graceful fallback when profile is missing or empty
- HMAC signature validation (valid, invalid, missing)
- Empty body handling

Run with:
    pytest test_intermediate.py
"""

import hashlib
import hmac
import json

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
    return srv.app


@pytest.fixture
def secret_app(monkeypatch):
    """Return the FastAPI app with WEBHOOK_SECRET=testsecret set."""
    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    import importlib
    import server as srv

    importlib.reload(srv)
    return srv.app


# ---------------------------------------------------------------------------
# Profile personalisation tests
# ---------------------------------------------------------------------------


async def test_reply_includes_user_name_from_profile(open_app):
    """When profile.name is present, the reply greets the user by name."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "Hello"},
                "profile": {"name": "Alice"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "Alice" in data["reply"]


async def test_reply_locale_spanish_when_locale_es(open_app):
    """When profile.locale is 'es', the greeting is in Spanish."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "Hola"},
                "profile": {"name": "Carlos", "locale": "es"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    reply = data["reply"].lower()
    # Spanish greeting: hola or bienvenido
    assert "hola" in reply or "bienvenido" in reply


async def test_reply_locale_french_when_locale_fr(open_app):
    """When profile.locale is 'fr', the greeting is in French."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "Bonjour"},
                "profile": {"name": "Marie", "locale": "fr"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    reply = data["reply"].lower()
    assert "bonjour" in reply or "bienvenue" in reply


async def test_reply_default_english_when_no_locale(open_app):
    """When no locale is provided the reply is in English."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "Hi"},
                "profile": {"name": "Bob"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    reply = data["reply"].lower()
    assert "hello" in reply or "hi" in reply or "welcome" in reply


async def test_graceful_fallback_when_profile_missing(open_app):
    """When profile is absent entirely, the server returns 200 with a generic reply."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={"message": {"content": "Hey there"}},
        )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 0


async def test_graceful_fallback_when_profile_empty(open_app):
    """When profile is an empty dict, the server returns 200 with a generic reply."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={"message": {"content": "Hey"}, "profile": {}},
        )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 0


# ---------------------------------------------------------------------------
# content_json card hint tests
# ---------------------------------------------------------------------------


async def test_content_json_suggestion_card_included_for_help_context(open_app):
    """When context.intent is 'help', content_json contains a suggestion card hint."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "I need help"},
                "profile": {"name": "Dana"},
                "context": {"intent": "help"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "content_json" in data
    cj = data["content_json"]
    assert cj.get("type") == "suggestion"
    assert "text" in cj


async def test_content_json_absent_when_no_special_context(open_app):
    """When no special context is provided, content_json is None or not a card hint."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "Just chatting"},
                "profile": {"name": "Eve"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    # content_json is present but should not be a suggestion card
    cj = data.get("content_json")
    if cj is not None:
        assert cj.get("type") != "suggestion"


async def test_content_json_product_card_for_product_intent(open_app):
    """When context.intent is 'product', content_json contains a product card hint."""
    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            json={
                "message": {"content": "Show me your products"},
                "profile": {"name": "Frank"},
                "context": {"intent": "product"},
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "content_json" in data
    cj = data["content_json"]
    assert cj.get("type") == "product_card"
    assert "items" in cj


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


# ---------------------------------------------------------------------------
# HMAC signature validation
# ---------------------------------------------------------------------------


async def test_valid_signature_passes(secret_app):
    """A correctly signed request is accepted."""
    payload = json.dumps(
        {"message": {"content": "hi"}, "profile": {"name": "Grace"}}
    ).encode()
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
