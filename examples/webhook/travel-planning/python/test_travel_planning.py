"""Tests for the Travel Planning webhook -- all mocked, no external API needed."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_app_module = None
_APP_DIR = Path(__file__).resolve().parent
_MODULE_NAME = "travel_planning_app"


def _get_app():
    global _app_module
    if _app_module is None:
        spec = importlib.util.spec_from_file_location(_MODULE_NAME, _APP_DIR / "app.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_MODULE_NAME] = mod
        spec.loader.exec_module(mod)
        _app_module = mod
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

    def test_root_service_name_contains_travel(self):
        client = _make_client()
        data = client.get("/").json()
        assert "travel" in data["service"].lower() or "travel" in data.get("description", "").lower()

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
        assert "trip_plan" in intents
        assert "flight_compare" in intents
        assert "booking_handoff" in intents
        assert "budget_check" in intents
        assert "disruption_replan" in intents

    def test_root_capabilities_states_match_contract(self):
        client = _make_client()
        data = client.get("/").json()
        states = {cap["intent"]: cap["state"] for cap in data["capabilities"]}
        assert states["trip_plan"] == "simulated"
        assert states["flight_compare"] == "simulated"
        assert states["booking_handoff"] == "requires_connector"
        assert states["budget_check"] == "simulated"
        assert states["disruption_replan"] == "simulated"

    def test_root_has_schema_version(self):
        client = _make_client()
        data = client.get("/").json()
        assert "schema_version" in data
        assert data["showcase"]["role"] == "flagship"

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
        assert data["name"] == "nexo-travel-planning"
        assert data["capabilities"]["items"][0]["name"] == "travel.planning"
        assert data["capabilities"]["items"][0]["metadata"]["showcase_role"] == "flagship"
        assert "travel-planner" in data["capabilities"]["items"][0]["metadata"]["supersedes"]


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_plan_keyword(self):
        m = _get_app()
        assert m.detect_intent("I want to plan a trip to Barcelona") == "trip_plan"

    def test_travel_keyword(self):
        m = _get_app()
        assert m.detect_intent("I am planning to travel to Tokyo") == "trip_plan"

    def test_destination_keyword(self):
        m = _get_app()
        assert m.detect_intent("What destination should I visit in summer?") == "trip_plan"

    def test_itinerary_keyword(self):
        m = _get_app()
        assert m.detect_intent("Create an itinerary for my trip") == "trip_plan"

    def test_flight_compare_keyword(self):
        m = _get_app()
        assert m.detect_intent("Compare flights to Lisbon next month") == "flight_compare"

    def test_booking_handoff_keyword(self):
        m = _get_app()
        assert m.detect_intent("I am ready to book now") == "booking_handoff"

    def test_budget_keyword(self):
        m = _get_app()
        assert m.detect_intent("Check my travel budget") == "budget_check"

    def test_how_much_keyword(self):
        m = _get_app()
        assert m.detect_intent("How much have I spent so far?") == "budget_check"

    def test_expense_keyword(self):
        m = _get_app()
        assert m.detect_intent("Show me my expense breakdown") == "budget_check"

    def test_over_budget_keyword(self):
        m = _get_app()
        assert m.detect_intent("Am I over budget for this trip?") == "budget_check"

    def test_delay_keyword(self):
        m = _get_app()
        assert m.detect_intent("My flight is delayed by 3 hours") == "disruption_replan"

    def test_cancelled_keyword(self):
        m = _get_app()
        assert m.detect_intent("My flight has been cancelled") == "disruption_replan"

    def test_rebook_keyword(self):
        m = _get_app()
        assert m.detect_intent("I need to rebook my flight") == "disruption_replan"

    def test_stranded_keyword(self):
        m = _get_app()
        assert m.detect_intent("I am stranded at the airport") == "disruption_replan"

    def test_unknown_falls_back_to_trip_plan(self):
        m = _get_app()
        assert m.detect_intent("Hello there, help me out") == "trip_plan"

    def test_case_insensitive(self):
        m = _get_app()
        assert m.detect_intent("PLAN MY TRIP TO LISBON") == "trip_plan"

    def test_disruption_takes_priority_over_budget(self):
        m = _get_app()
        # "cancelled budget" - disruption wins
        assert m.detect_intent("my flight was cancelled what is the cost to rebook") == "disruption_replan"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestExtractTripDays:
    def test_explicit_days(self):
        m = _get_app()
        assert m._extract_trip_days("I want a 10 day trip") == 10

    def test_explicit_nights(self):
        m = _get_app()
        assert m._extract_trip_days("Book 5 nights for me") == 5

    def test_weeks_converted(self):
        m = _get_app()
        assert m._extract_trip_days("Plan a 2 week trip") == 14

    def test_default_7_when_no_duration(self):
        m = _get_app()
        assert m._extract_trip_days("Plan a trip to Barcelona") == 7


class TestGetBudgetTier:
    def test_luxury_detected(self):
        m = _get_app()
        assert m._get_budget_tier("I want a luxury holiday") == "luxury"

    def test_budget_detected(self):
        m = _get_app()
        assert m._get_budget_tier("Cheap backpacker trip") == "budget"

    def test_mid_range_default(self):
        m = _get_app()
        assert m._get_budget_tier("Plan my trip") == "mid-range"

    def test_premium_detected_as_luxury(self):
        m = _get_app()
        assert m._get_budget_tier("I prefer premium hotels") == "luxury"

    def test_extract_budget_tier_returns_none_for_generic_query(self):
        m = _get_app()
        assert m._extract_budget_tier("Plan my trip") is None


class TestGetDestinationData:
    def test_barcelona_recognised(self):
        m = _get_app()
        data = m._get_destination_data("I want to visit Barcelona")
        assert "Barcelona" in data["name"]

    def test_tokyo_recognised(self):
        m = _get_app()
        data = m._get_destination_data("Trip to Tokyo please")
        assert "Tokyo" in data["name"]

    def test_lisbon_recognised(self):
        m = _get_app()
        data = m._get_destination_data("Let us go to Lisbon")
        assert "Lisbon" in data["name"]

    def test_unknown_destination_returns_default(self):
        m = _get_app()
        data = m._get_destination_data("I want to go somewhere")
        assert data == m._DESTINATIONS["default"]


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


class TestTripPlanCard:
    def _make_card(self):
        m = _get_app()
        dest = m._DESTINATIONS["barcelona"]
        budget = m._BUDGET_TEMPLATES["mid-range"]
        return m.build_trip_plan_card(dest, budget, days=7)

    def test_type_is_trip_plan(self):
        assert self._make_card()["type"] == "trip_plan"

    def test_has_title(self):
        card = self._make_card()
        assert "title" in card
        assert len(card["title"]) > 0

    def test_has_fields(self):
        card = self._make_card()
        assert "fields" in card
        assert len(card["fields"]) > 0

    def test_metadata_capability_simulated(self):
        card = self._make_card()
        assert card["metadata"]["capability_state"] == "simulated"

    def test_fields_contain_destination(self):
        card = self._make_card()
        labels = [f["label"] for f in card["fields"]]
        assert "Destination" in labels

    def test_fields_contain_estimated_total(self):
        card = self._make_card()
        labels = [f["label"] for f in card["fields"]]
        assert "Estimated total" in labels

    def test_estimated_total_has_eur(self):
        card = self._make_card()
        total_fields = [f for f in card["fields"] if f["label"] == "Estimated total"]
        assert len(total_fields) == 1
        assert "EUR" in total_fields[0]["value"]

    def test_subtitle_mentions_days(self):
        card = self._make_card()
        assert "7" in card["subtitle"] or "day" in card["subtitle"].lower()


class TestBudgetCheckCard:
    def test_type_is_budget_check(self):
        m = _get_app()
        card = m.build_budget_check_card(budget_total=1500.0, spent=975.0)
        assert card["type"] == "budget_check"

    def test_has_title(self):
        m = _get_app()
        card = m.build_budget_check_card(1500.0, 975.0)
        assert "title" in card

    def test_metadata_capability_simulated(self):
        m = _get_app()
        card = m.build_budget_check_card(1500.0, 975.0)
        assert card["metadata"]["capability_state"] == "simulated"

    def test_status_field_present(self):
        m = _get_app()
        card = m.build_budget_check_card(1500.0, 975.0)
        labels = [f["label"] for f in card["fields"]]
        assert "Status" in labels

    def test_over_budget_shows_warning(self):
        m = _get_app()
        card = m.build_budget_check_card(1000.0, 1200.0)
        status_fields = [f for f in card["fields"] if f["label"] == "Status"]
        assert "over" in status_fields[0]["value"].lower()

    def test_within_budget_shows_on_track(self):
        m = _get_app()
        card = m.build_budget_check_card(1500.0, 500.0)
        status_fields = [f for f in card["fields"] if f["label"] == "Status"]
        assert "track" in status_fields[0]["value"].lower()

    def test_saving_tip_present(self):
        m = _get_app()
        card = m.build_budget_check_card(1500.0, 975.0)
        labels = [f["label"] for f in card["fields"]]
        assert "Saving tip" in labels


class TestDisruptionCard:
    def test_type_is_disruption_alert(self):
        m = _get_app()
        card = m.build_disruption_card()
        assert card["type"] == "disruption_alert"

    def test_has_title(self):
        m = _get_app()
        card = m.build_disruption_card()
        assert "title" in card

    def test_metadata_capability_simulated(self):
        m = _get_app()
        card = m.build_disruption_card()
        assert card["metadata"]["capability_state"] == "simulated"

    def test_has_alert_type_field(self):
        m = _get_app()
        card = m.build_disruption_card()
        labels = [f["label"] for f in card["fields"]]
        assert "Alert type" in labels

    def test_has_options(self):
        m = _get_app()
        card = m.build_disruption_card()
        option_fields = [f for f in card["fields"] if f["label"].startswith("Option")]
        assert len(option_fields) >= 2

    def test_cancellation_scenario_index_1(self):
        m = _get_app()
        card = m.build_disruption_card(scenario_index=1)
        alert_fields = [f for f in card["fields"] if f["label"] == "Alert type"]
        assert "cancel" in alert_fields[0]["value"].lower()

    def test_out_of_bounds_index_clamps(self):
        m = _get_app()
        card = m.build_disruption_card(scenario_index=99)
        assert card["type"] == "disruption_alert"


# ---------------------------------------------------------------------------
# Webhook endpoint -- trip plan
# ---------------------------------------------------------------------------


class TestWebhookTripPlan:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Let me plan that trip for you!"):
            resp = client.post("/", json=_webhook_payload("Plan a trip to Barcelona for 7 days"))
        assert resp.status_code == 200

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="trip"):
            resp = client.post("/", json=_webhook_payload("plan my holiday"))
        data = resp.json()
        assert data["schema_version"] == "2026-03"
        assert data["task"]["status"] == "completed"
        assert data["capability"]["name"] == "travel.planning"
        assert isinstance(data["artifacts"], list)

    def test_status_completed(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="trip"):
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        assert resp.json()["status"] == "completed"

    def test_has_content_parts(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is your trip plan!"):
            resp = client.post("/", json=_webhook_payload("plan a trip to Tokyo"))
        data = resp.json()
        assert len(data["content_parts"]) > 0

    def test_has_trip_plan_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="trip"):
            resp = client.post("/", json=_webhook_payload("I want to travel to Barcelona"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "trip_plan" for c in cards)

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="trip"):
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        assert len(resp.json().get("actions", [])) > 0

    def test_capability_state_in_card_metadata(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="trip"):
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        cards = resp.json().get("cards", [])
        for card in cards:
            assert card.get("metadata", {}).get("capability_state") == "simulated"

    def test_has_prompt_suggestions_metadata(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="trip"):
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        suggestions = resp.json().get("metadata", {}).get("prompt_suggestions", [])
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0

    def test_personalisation_display_name(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Hello!"):
            resp = client.post("/", json=_webhook_payload(
                "plan a trip to Lisbon",
                profile={"display_name": "Sara"},
            ))
        text = resp.json()["content_parts"][0]["text"]
        assert "Sara" in text

    def test_no_name_no_prefix(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is your trip."):
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        text = resp.json()["content_parts"][0]["text"]
        assert not text.startswith("Hey ")

    def test_uses_profile_budget_when_query_has_no_budget_hint(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is your trip."):
            resp = client.post(
                "/",
                json=_webhook_payload(
                    "plan a trip to Lisbon",
                    profile={"preferences": {"budget": "high"}},
                ),
            )
        trip_card = next(c for c in resp.json()["cards"] if c["type"] == "trip_plan")
        budget_field = next(f for f in trip_card["fields"] if f["label"] == "Budget Tier")
        assert "luxury" in budget_field["value"].lower()
        assert resp.json()["metadata"]["personalization"]["used"]["preferences.budget"] == "luxury"

    def test_generic_mode_when_budget_preference_missing(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is your trip."):
            resp = client.post("/", json=_webhook_payload("plan a trip to Lisbon"))
        assert resp.json()["metadata"]["personalization"]["mode"] == "generic"

    def test_locale_instruction_added_to_system_prompt(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        captured: dict[str, str] = {}

        async def _fake_call(system_prompt: str, user_message: str) -> str:
            captured["system_prompt"] = system_prompt
            return "Trip ready."

        with patch.object(m, "call_llm", side_effect=_fake_call):
            resp = client.post(
                "/",
                json=_webhook_payload(
                    "plan a trip to Lisbon",
                    profile={"display_name": "Sara", "locale": "pt-BR"},
                ),
            )

        assert resp.status_code == 200
        assert "preferred language (pt-BR)" in captured["system_prompt"]


class TestWebhookFlightCompare:
    def test_returns_flight_compare_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here are the best flight options."):
            resp = client.post("/", json=_webhook_payload("Compare flights to Lisbon next month"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "flight_compare" for c in cards)


class TestWebhookBookingHandoff:
    def test_returns_booking_handoff_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Your booking handoff is ready."):
            resp = client.post("/", json=_webhook_payload("Prepare booking handoff for Barcelona"))
        cards = resp.json().get("cards", [])
        handoff = next(c for c in cards if c["type"] == "booking_handoff")
        assert handoff["metadata"]["capability_state"] == "requires_connector"


# ---------------------------------------------------------------------------
# Webhook endpoint -- budget check
# ---------------------------------------------------------------------------


class TestWebhookBudgetCheck:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Budget looks good."):
            resp = client.post("/", json=_webhook_payload("check my budget"))
        assert resp.status_code == 200

    def test_has_budget_check_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="budget"):
            resp = client.post("/", json=_webhook_payload("how much have I spent"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "budget_check" for c in cards)

    def test_budget_card_has_status_field(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="budget"):
            resp = client.post("/", json=_webhook_payload("check my budget"))
        cards = resp.json().get("cards", [])
        budget_cards = [c for c in cards if c["type"] == "budget_check"]
        assert len(budget_cards) == 1
        labels = [f["label"] for f in budget_cards[0]["fields"]]
        assert "Status" in labels

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="budget"):
            resp = client.post("/", json=_webhook_payload("what is my expense total"))
        assert len(resp.json().get("actions", [])) > 0

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("show my spend"))
        assert resp.json()["schema_version"] == "2026-03"

    def test_capability_state_in_card_metadata(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="budget"):
            resp = client.post("/", json=_webhook_payload("check my travel budget"))
        cards = resp.json().get("cards", [])
        for card in cards:
            assert card.get("metadata", {}).get("capability_state") == "simulated"


# ---------------------------------------------------------------------------
# Webhook endpoint -- disruption replan
# ---------------------------------------------------------------------------


class TestWebhookDisruptionReplan:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Let me help with your disruption."):
            resp = client.post("/", json=_webhook_payload("my flight is delayed"))
        assert resp.status_code == 200

    def test_has_disruption_alert_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="disruption"):
            resp = client.post("/", json=_webhook_payload("my flight has been cancelled"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "disruption_alert" for c in cards)

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="disruption"):
            resp = client.post("/", json=_webhook_payload("flight delayed"))
        assert len(resp.json().get("actions", [])) > 0

    def test_status_completed(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="disruption"):
            resp = client.post("/", json=_webhook_payload("my flight was cancelled"))
        assert resp.json()["status"] == "completed"

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("need to rebook flight"))
        assert resp.json()["schema_version"] == "2026-03"

    def test_disruption_card_has_options(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="disruption"):
            resp = client.post("/", json=_webhook_payload("flight is delayed"))
        cards = resp.json().get("cards", [])
        disruption_cards = [c for c in cards if c["type"] == "disruption_alert"]
        assert len(disruption_cards) == 1
        option_fields = [f for f in disruption_cards[0]["fields"] if f["label"].startswith("Option")]
        assert len(option_fields) >= 2

    def test_personalisation(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="We will sort this out!"):
            resp = client.post("/", json=_webhook_payload(
                "my flight was delayed",
                profile={"display_name": "Carlos"},
            ))
        text = resp.json()["content_parts"][0]["text"]
        assert "Carlos" in text

    def test_cancellation_keyword_uses_cancellation_scenario(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="disruption"):
            resp = client.post("/", json=_webhook_payload("my flight has been cancelled"))
        cards = resp.json().get("cards", [])
        disruption_cards = [c for c in cards if c["type"] == "disruption_alert"]
        assert len(disruption_cards) == 1
        alert_type_fields = [f for f in disruption_cards[0]["fields"] if f["label"] == "Alert type"]
        assert "cancel" in alert_type_fields[0]["value"].lower()


# ---------------------------------------------------------------------------
# HMAC signature
# ---------------------------------------------------------------------------


class TestHMACSignature:
    def test_valid_signature_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "test-secret")
        body = json.dumps(_webhook_payload("plan a trip to Barcelona"))
        ts = "1700000000"
        sig = _sign("test-secret", ts, body)
        with patch.object(m, "call_llm", return_value="trip"):
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
        body = json.dumps(_webhook_payload("plan a trip"))
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
        resp = client.post("/", json=_webhook_payload("plan a trip"))
        assert resp.status_code == 401

    def test_no_secret_skips_verification(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        assert resp.status_code == 200

    def test_wrong_secret_401(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "correct-secret")
        body = json.dumps(_webhook_payload("plan a trip"))
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
            yield f"data: {json.dumps({'type': 'delta', 'text': 'planning'})}\n\n"

        with patch.object(m, "stream_llm", side_effect=_fake_stream):
            resp = client.post(
                "/",
                json=_webhook_payload("plan a trip"),
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
                json=_webhook_payload("plan a trip"),
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
        assert done["schema_version"] == "2026-03"
        assert done["capability"]["name"] == "travel.planning"
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
                json=_webhook_payload("plan a trip"),
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
            resp = client.post("/", json=_webhook_payload("plan a trip"))
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_stream_disabled_returns_json(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", False)
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post(
                "/",
                json=_webhook_payload("plan a trip"),
                headers={"Accept": "text/event-stream"},
            )
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_sse_personalisation_prefix(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'trip planned'})}\n\n"

        with patch.object(m, "stream_llm", side_effect=_fake_stream):
            resp = client.post(
                "/",
                json=_webhook_payload("plan my trip", profile={"display_name": "Elena"}),
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
