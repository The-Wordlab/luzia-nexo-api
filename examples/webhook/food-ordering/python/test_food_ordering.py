"""Tests for the Food Ordering webhook -- all mocked, no external API needed."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_app_module = None


def _get_app():
    global _app_module
    if _app_module is None:
        import app as _am
        _app_module = _am
    return _app_module


def _make_client() -> TestClient:
    m = _get_app()
    return TestClient(m.app, raise_server_exceptions=False)


def _sign(secret: str, timestamp: str, body: str) -> str:
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _webhook_payload(content: str, **extra) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event": "message_created",
        "app": {},
        "thread": {},
        "message": {"role": "user", "content": content},
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------


class TestRoot:
    def test_root_200(self):
        client = _make_client()
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_has_service_field(self):
        client = _make_client()
        data = client.get("/").json()
        assert "service" in data

    def test_root_service_name(self):
        client = _make_client()
        data = client.get("/").json()
        assert "food" in data["service"].lower() or "food" in data.get("description", "").lower()

    def test_root_lists_routes(self):
        client = _make_client()
        data = client.get("/").json()
        assert "routes" in data
        paths = [r["path"] for r in data["routes"]]
        assert "/" in paths
        assert "/health" in paths
        assert "/ingest" in paths

    def test_root_lists_capabilities(self):
        client = _make_client()
        data = client.get("/").json()
        assert "capabilities" in data
        intents = [c["intent"] for c in data["capabilities"]]
        assert "menu_browse" in intents
        assert "order_build" in intents
        assert "order_track" in intents

    def test_root_capabilities_all_simulated(self):
        client = _make_client()
        data = client.get("/").json()
        for cap in data["capabilities"]:
            assert cap["state"] == "simulated"

    def test_health_200(self):
        client = _make_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status(self):
        client = _make_client()
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_has_timestamp(self):
        client = _make_client()
        data = client.get("/health").json()
        assert "timestamp" in data

    def test_ingest_placeholder_200(self):
        client = _make_client()
        resp = client.post("/ingest", json={"items": []})
        assert resp.status_code == 200

    def test_ingest_returns_ok(self):
        client = _make_client()
        data = client.post("/ingest", json={}).json()
        assert data["status"] == "ok"

    def test_agent_card_endpoint(self):
        client = _make_client()
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "nexo-food-ordering"
        assert data["capabilities"]["items"][0]["name"] == "food.ordering"
        assert data["capabilities"]["items"][0]["metadata"]["showcase_role"] == "flagship"


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_menu_keyword(self):
        m = _get_app()
        assert m.detect_intent("Show me the menu") == "menu_browse"

    def test_available_keyword(self):
        m = _get_app()
        assert m.detect_intent("What's available to eat?") == "menu_browse"

    def test_vegan_keyword(self):
        m = _get_app()
        assert m.detect_intent("Show me vegan options") == "menu_browse"

    def test_vegetarian_keyword(self):
        m = _get_app()
        assert m.detect_intent("I want vegetarian food") == "menu_browse"

    def test_order_keyword(self):
        m = _get_app()
        assert m.detect_intent("I want to order a pizza") == "order_build"

    def test_add_to_cart_keyword(self):
        m = _get_app()
        assert m.detect_intent("Add the burger to my cart") == "order_build"

    def test_confirm_keyword(self):
        m = _get_app()
        assert m.detect_intent("Confirm my order please") == "order_build"

    def test_track_keyword(self):
        m = _get_app()
        assert m.detect_intent("Track my order") == "order_track"

    def test_delivery_status_keyword(self):
        m = _get_app()
        assert m.detect_intent("Where is my delivery?") == "order_track"

    def test_on_the_way_keyword(self):
        m = _get_app()
        assert m.detect_intent("Is it on the way?") == "order_track"

    def test_unknown_falls_back_to_menu(self):
        m = _get_app()
        assert m.detect_intent("Hello there") == "menu_browse"

    def test_case_insensitive(self):
        m = _get_app()
        assert m.detect_intent("SHOW ME THE MENU") == "menu_browse"

    def test_track_takes_priority_over_order(self):
        m = _get_app()
        # "track my order" has both track and order keywords - track wins
        assert m.detect_intent("track my order status") == "order_track"

    def test_discovery_prompt_with_delivery_stays_menu_browse(self):
        m = _get_app()
        assert m.detect_intent("show me nearby vegetarian delivery for tonight") == "menu_browse"


# ---------------------------------------------------------------------------
# Dietary filter extraction
# ---------------------------------------------------------------------------


class TestExtractDietaryFilter:
    def test_vegan_detected(self):
        m = _get_app()
        assert m._extract_dietary_filter("show me vegan options") == "vegan"

    def test_vegetarian_detected(self):
        m = _get_app()
        assert m._extract_dietary_filter("vegetarian dishes only") == "vegetarian"

    def test_gluten_free_detected(self):
        m = _get_app()
        assert m._extract_dietary_filter("gluten-free meals please") == "gluten-free"

    def test_no_filter_returns_none(self):
        m = _get_app()
        assert m._extract_dietary_filter("show me the menu") is None

    def test_case_insensitive(self):
        m = _get_app()
        assert m._extract_dietary_filter("VEGAN OPTIONS") == "vegan"


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


class TestMenuCard:
    def test_type_is_menu(self):
        m = _get_app()
        card = m.build_menu_card()
        assert card["type"] == "menu"

    def test_has_title(self):
        m = _get_app()
        card = m.build_menu_card()
        assert "title" in card
        assert len(card["title"]) > 0

    def test_has_fields(self):
        m = _get_app()
        card = m.build_menu_card()
        assert "fields" in card
        assert len(card["fields"]) > 0

    def test_metadata_capability_simulated(self):
        m = _get_app()
        card = m.build_menu_card()
        assert card["metadata"]["capability_state"] == "simulated"

    def test_vegan_filter(self):
        m = _get_app()
        card = m.build_menu_card(filter_dietary="vegan")
        # All fields should contain vegan items
        assert len(card["fields"]) > 0
        for field in card["fields"]:
            assert "vegan" in field["value"].lower()

    def test_no_filter_returns_all_items(self):
        m = _get_app()
        card = m.build_menu_card()
        assert len(card["fields"]) == len(m._MENU_ITEMS)

    def test_unknown_filter_shows_no_items_message(self):
        m = _get_app()
        card = m.build_menu_card(filter_dietary="keto")
        assert len(card["fields"]) == 1
        assert "no items" in card["fields"][0]["label"].lower()

    def test_fields_contain_price(self):
        m = _get_app()
        card = m.build_menu_card()
        for field in card["fields"]:
            assert "$" in field["label"]

    def test_subtitle_mentions_filter_when_set(self):
        m = _get_app()
        card = m.build_menu_card(filter_dietary="vegan")
        assert "vegan" in card["subtitle"].lower()


class TestRestaurantShortlistCard:
    def test_type_is_restaurant_shortlist(self):
        m = _get_app()
        card = m.build_restaurant_shortlist_card()
        assert card["type"] == "restaurant_shortlist"

    def test_location_and_filter_appear_in_subtitle(self):
        m = _get_app()
        card = m.build_restaurant_shortlist_card(location_hint="Madrid", dietary_filter="vegetarian")
        assert "Madrid" in card["subtitle"]
        assert "vegetarian" in card["subtitle"].lower()


class TestOrderSummaryCard:
    def test_type_is_order_summary(self):
        m = _get_app()
        items = [{"name": "Pizza", "price": 12.99, "qty": 1}]
        card = m.build_order_summary_card(items, total=12.99)
        assert card["type"] == "order_summary"

    def test_has_title(self):
        m = _get_app()
        items = [{"name": "Pizza", "price": 12.99, "qty": 1}]
        card = m.build_order_summary_card(items, total=12.99)
        assert "title" in card

    def test_has_total_field(self):
        m = _get_app()
        items = [{"name": "Pizza", "price": 12.99, "qty": 1}]
        card = m.build_order_summary_card(items, total=12.99)
        labels = [f["label"] for f in card["fields"]]
        assert "Total" in labels

    def test_metadata_capability_simulated(self):
        m = _get_app()
        items = [{"name": "Pizza", "price": 12.99, "qty": 1}]
        card = m.build_order_summary_card(items, total=12.99)
        assert card["metadata"]["capability_state"] == "simulated"

    def test_notes_appear_in_fields(self):
        m = _get_app()
        items = [{"name": "Pizza", "price": 12.99, "qty": 1}]
        card = m.build_order_summary_card(items, total=12.99, notes="No onions")
        labels = [f["label"] for f in card["fields"]]
        assert "Notes" in labels

    def test_no_notes_no_notes_field(self):
        m = _get_app()
        items = [{"name": "Pizza", "price": 12.99, "qty": 1}]
        card = m.build_order_summary_card(items, total=12.99)
        labels = [f["label"] for f in card["fields"]]
        assert "Notes" not in labels

    def test_multiple_items_all_appear(self):
        m = _get_app()
        items = [
            {"name": "Pizza", "price": 12.99, "qty": 1},
            {"name": "Soup", "price": 8.50, "qty": 2},
        ]
        card = m.build_order_summary_card(items, total=29.99)
        item_labels = [f["label"] for f in card["fields"] if f["label"] not in ("Total", "Notes")]
        assert len(item_labels) == 2


class TestOrderStatusCard:
    def test_type_is_order_status(self):
        m = _get_app()
        card = m.build_order_status_card()
        assert card["type"] == "order_status"

    def test_has_title(self):
        m = _get_app()
        card = m.build_order_status_card()
        assert "title" in card

    def test_has_status_field(self):
        m = _get_app()
        card = m.build_order_status_card()
        labels = [f["label"] for f in card["fields"]]
        assert "Status" in labels

    def test_has_order_id_field(self):
        m = _get_app()
        card = m.build_order_status_card()
        labels = [f["label"] for f in card["fields"]]
        assert "Order ID" in labels

    def test_metadata_capability_simulated(self):
        m = _get_app()
        card = m.build_order_status_card()
        assert card["metadata"]["capability_state"] == "simulated"

    def test_preparing_status(self):
        m = _get_app()
        card = m.build_order_status_card(status_index=0)
        status_values = [f["value"] for f in card["fields"] if f["label"] == "Status"]
        assert any("preparing" in v.lower() for v in status_values)

    def test_out_of_bounds_index_clamps(self):
        m = _get_app()
        card = m.build_order_status_card(status_index=99)
        assert card["type"] == "order_status"


# ---------------------------------------------------------------------------
# Webhook endpoint -- menu browse
# ---------------------------------------------------------------------------


class TestWebhookMenuBrowse:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is our menu!"):
            resp = client.post("/", json=_webhook_payload("show me the menu"))
        assert resp.status_code == 200

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="menu text"):
            resp = client.post("/", json=_webhook_payload("menu"))
        data = resp.json()
        assert data["schema_version"] == "2026-03-01"
        assert data["task"]["status"] == "completed"
        assert data["capability"]["name"] == "food.ordering"
        assert isinstance(data["artifacts"], list)

    def test_status_completed(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="menu"):
            resp = client.post("/", json=_webhook_payload("menu"))
        assert resp.json()["status"] == "completed"

    def test_has_content_parts(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is our menu!"):
            resp = client.post("/", json=_webhook_payload("show me what you have"))
        data = resp.json()
        assert len(data["content_parts"]) > 0

    def test_has_menu_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="menu"):
            resp = client.post("/", json=_webhook_payload("show me the menu"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "menu" for c in cards)
        assert any(c["type"] == "restaurant_shortlist" for c in cards)

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="menu"):
            resp = client.post("/", json=_webhook_payload("show me the menu"))
        assert len(resp.json().get("actions", [])) > 0

    def test_vegan_filter_applied(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="vegan options"):
            resp = client.post("/", json=_webhook_payload("show me vegan options"))
        cards = resp.json().get("cards", [])
        menu_cards = [c for c in cards if c["type"] == "menu"]
        assert len(menu_cards) == 1
        assert "vegan" in menu_cards[0]["subtitle"].lower()

    def test_personalisation_display_name(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Hello!"):
            resp = client.post("/", json=_webhook_payload(
                "show me the menu",
                profile={"display_name": "Maria"},
            ))
        text = resp.json()["content_parts"][0]["text"]
        assert "Maria" in text

    def test_uses_profile_dietary_preference_when_query_is_generic(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here are your options."):
            resp = client.post(
                "/",
                json=_webhook_payload(
                    "show me the menu",
                    profile={"preferences": {"dietary": "vegetarian"}},
                ),
            )
        menu_card = next(c for c in resp.json()["cards"] if c["type"] == "menu")
        assert "vegetarian" in menu_card["subtitle"].lower()
        assert resp.json()["metadata"]["personalization"]["used"]["preferences.dietary"] == "vegetarian"

    def test_uses_cuisine_and_location_context_for_shortlist(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here are your best matches."):
            resp = client.post(
                "/",
                json=_webhook_payload(
                    "show me dinner options",
                    profile={
                        "city": "Madrid",
                        "preferences": {"cuisine": "italian"},
                    },
                ),
            )
        shortlist = next(c for c in resp.json()["cards"] if c["type"] == "restaurant_shortlist")
        assert "Madrid" in shortlist["subtitle"]
        used = resp.json()["metadata"]["personalization"]["used"]
        assert used["preferences.cuisine"] == "italian"
        assert used["location_hint"] == "Madrid"

    def test_no_name_no_prefix(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is our menu."):
            resp = client.post("/", json=_webhook_payload("show me the menu"))
        text = resp.json()["content_parts"][0]["text"]
        assert not text.startswith("Hey ")

    def test_generic_mode_when_profile_preferences_absent(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is the menu."):
            resp = client.post("/", json=_webhook_payload("show me the menu"))
        assert resp.json()["metadata"]["personalization"]["mode"] == "generic"


# ---------------------------------------------------------------------------
# Webhook endpoint -- order build
# ---------------------------------------------------------------------------


class TestWebhookOrderBuild:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Order ready to confirm."):
            resp = client.post("/", json=_webhook_payload("I want to order a pizza"))
        assert resp.status_code == 200

    def test_has_order_summary_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="order summary"):
            resp = client.post("/", json=_webhook_payload("add pizza to cart"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "order_summary" for c in cards)

    def test_confirm_and_modify_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="order"):
            resp = client.post("/", json=_webhook_payload("place my order"))
        actions = resp.json().get("actions", [])
        labels = [a.get("label", "").lower() for a in actions]
        assert any("approve" in l for l in labels)
        assert any("modify" in l for l in labels)

    def test_checkout_artifact_requires_approval(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="order"):
            resp = client.post("/", json=_webhook_payload("place my order"))
        artifact = next(a for a in resp.json()["artifacts"] if a["name"] == "checkout_package")
        assert artifact["data"]["approval_required"] is True

    def test_order_summary_has_total(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="order"):
            resp = client.post("/", json=_webhook_payload("order food"))
        cards = resp.json().get("cards", [])
        summary_cards = [c for c in cards if c["type"] == "order_summary"]
        assert len(summary_cards) == 1
        field_labels = [f["label"] for f in summary_cards[0]["fields"]]
        assert "Total" in field_labels

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("buy something"))
        assert resp.json()["schema_version"] == "2026-03-01"

    def test_capability_state_in_card_metadata(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="order"):
            resp = client.post("/", json=_webhook_payload("i'd like to order"))
        cards = resp.json().get("cards", [])
        for card in cards:
            assert card.get("metadata", {}).get("capability_state") == "simulated"

    def test_has_prompt_suggestions_metadata(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="order"):
            resp = client.post("/", json=_webhook_payload("i'd like to order"))
        suggestions = resp.json().get("metadata", {}).get("prompt_suggestions", [])
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0

    def test_uses_profile_budget_preference_for_order_draft(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Order ready."):
            resp = client.post(
                "/",
                json=_webhook_payload(
                    "build my order",
                    profile={"preferences": {"budget": "low"}},
                ),
            )
        summary_card = next(c for c in resp.json()["cards"] if c["type"] == "order_summary")
        notes_field = next((f for f in summary_card["fields"] if f["label"] == "Notes"), None)
        assert notes_field is not None
        assert "budget" in notes_field["value"].lower()
        assert resp.json()["metadata"]["personalization"]["used"]["preferences.budget"] == "low"


# ---------------------------------------------------------------------------
# Webhook endpoint -- order track
# ---------------------------------------------------------------------------


class TestWebhookOrderTrack:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Your order is on its way!"):
            resp = client.post("/", json=_webhook_payload("track my order"))
        assert resp.status_code == 200

    def test_has_order_status_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="tracking"):
            resp = client.post("/", json=_webhook_payload("where is my delivery"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "order_status" for c in cards)

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="tracking"):
            resp = client.post("/", json=_webhook_payload("track my order"))
        assert len(resp.json().get("actions", [])) > 0

    def test_status_completed(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="tracking"):
            resp = client.post("/", json=_webhook_payload("track my order"))
        assert resp.json()["status"] == "completed"

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("delivery status"))
        assert resp.json()["schema_version"] == "2026-03-01"

    def test_order_status_has_order_id(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="tracking"):
            resp = client.post("/", json=_webhook_payload("track my order"))
        cards = resp.json().get("cards", [])
        status_cards = [c for c in cards if c["type"] == "order_status"]
        assert len(status_cards) == 1
        field_labels = [f["label"] for f in status_cards[0]["fields"]]
        assert "Order ID" in field_labels

    def test_personalisation(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Your order is on its way!"):
            resp = client.post("/", json=_webhook_payload(
                "track my order",
                profile={"display_name": "Carlos"},
            ))
        text = resp.json()["content_parts"][0]["text"]
        assert "Carlos" in text


# ---------------------------------------------------------------------------
# HMAC signature
# ---------------------------------------------------------------------------


class TestHMACSignature:
    def test_valid_signature_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "test-secret")
        body = json.dumps(_webhook_payload("show me the menu"))
        ts = "1700000000"
        sig = _sign("test-secret", ts, body)
        with patch.object(m, "call_llm", return_value="menu"):
            resp = client.post(
                "/",
                data=body,
                headers={"Content-Type": "application/json", "x-timestamp": ts, "x-signature": sig},
            )
        assert resp.status_code == 200

    def test_invalid_signature_401(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "test-secret")
        body = json.dumps(_webhook_payload("menu"))
        resp = client.post(
            "/",
            data=body,
            headers={"Content-Type": "application/json", "x-timestamp": "123", "x-signature": "sha256=wrong"},
        )
        assert resp.status_code == 401

    def test_missing_signature_401(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "test-secret")
        resp = client.post("/", json=_webhook_payload("menu"))
        assert resp.status_code == 401

    def test_no_secret_skips_verification(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("menu"))
        assert resp.status_code == 200

    def test_wrong_secret_401(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "correct-secret")
        body = json.dumps(_webhook_payload("menu"))
        ts = "1700000000"
        sig = _sign("wrong-secret", ts, body)
        resp = client.post(
            "/",
            data=body,
            headers={"Content-Type": "application/json", "x-timestamp": ts, "x-signature": sig},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------


class TestSSEStreaming:
    def test_stream_with_accept_header(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'hello'})}\n\n"

        with patch.object(m, "stream_llm", side_effect=_fake_stream):
            resp = client.post(
                "/",
                json=_webhook_payload("show me the menu"),
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert "event: task.started" in resp.text
        assert "event: task.delta" in resp.text

    def test_sse_done_event_has_cards(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'ok'})}\n\n"

        with patch.object(m, "stream_llm", side_effect=_fake_stream):
            resp = client.post(
                "/",
                json=_webhook_payload("menu"),
                headers={"Accept": "text/event-stream"},
            )

        events = []
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) >= 1
        done = done_events[-1]
        assert "cards" in done
        assert "actions" in done
        assert done["schema_version"] == "2026-03-01"
        assert done["capability"]["name"] == "food.ordering"
        assert isinstance(done["artifacts"], list)
        assert isinstance(done.get("metadata", {}).get("prompt_suggestions", []), list)

    def test_sse_done_event_status_completed(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'ok'})}\n\n"

        with patch.object(m, "stream_llm", side_effect=_fake_stream):
            resp = client.post(
                "/",
                json=_webhook_payload("menu"),
                headers={"Accept": "text/event-stream"},
            )

        events = [
            json.loads(line[len("data:"):].strip())
            for line in resp.text.splitlines()
            if line.startswith("data:")
        ]
        done = next((e for e in events if e.get("type") == "done"), None)
        assert done is not None
        assert done["status"] == "completed"

    def test_json_fallback_when_no_accept(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("menu"))
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_stream_disabled_returns_json(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", False)
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post(
                "/",
                json=_webhook_payload("menu"),
                headers={"Accept": "text/event-stream"},
            )
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_sse_personalisation_prefix(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'menu here'})}\n\n"

        with patch.object(m, "stream_llm", side_effect=_fake_stream):
            resp = client.post(
                "/",
                json=_webhook_payload("show me the menu", profile={"display_name": "Elena"}),
                headers={"Accept": "text/event-stream"},
            )

        events = [
            json.loads(line[len("data:"):].strip())
            for line in resp.text.splitlines()
            if line.startswith("data:")
        ]
        delta_texts = [e.get("text", "") for e in events if e.get("type") == "delta"]
        full_text = "".join(delta_texts)
        assert "Elena" in full_text


# ---------------------------------------------------------------------------
# Empty message guard
# ---------------------------------------------------------------------------


class TestEmptyMessage:
    def test_empty_content_400(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        resp = client.post("/", json=_webhook_payload(""))
        assert resp.status_code == 400

    def test_error_field_in_response(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        resp = client.post("/", json=_webhook_payload(""))
        assert "error" in resp.json()
