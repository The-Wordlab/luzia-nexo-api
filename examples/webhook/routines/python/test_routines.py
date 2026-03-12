"""Tests for the Daily Routines webhook — all mocked, no external API needed."""

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

    def test_root_lists_routes(self):
        client = _make_client()
        data = client.get("/").json()
        assert "routes" in data
        paths = [r["path"] for r in data["routes"]]
        assert "/" in paths
        assert "/health" in paths
        assert "/ingest" in paths

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


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_morning_briefing_keyword(self):
        m = _get_app()
        assert m.detect_intent("Good morning, what's my briefing?") == "morning_briefing"

    def test_morning_keyword_only(self):
        m = _get_app()
        assert m.detect_intent("morning") == "morning_briefing"

    def test_briefing_keyword(self):
        m = _get_app()
        assert m.detect_intent("Give me my daily briefing") == "morning_briefing"

    def test_schedule_keyword(self):
        m = _get_app()
        assert m.detect_intent("Add a meeting to my schedule") == "schedule_management"

    def test_calendar_keyword(self):
        m = _get_app()
        assert m.detect_intent("What's on my calendar today?") == "schedule_management"

    def test_reminder_keyword(self):
        m = _get_app()
        assert m.detect_intent("Set a reminder for my dentist") == "follow_up"

    def test_follow_up_keyword(self):
        m = _get_app()
        assert m.detect_intent("Follow up with the team about the report") == "follow_up"

    def test_unknown_falls_back_to_morning(self):
        m = _get_app()
        # Ambiguous message defaults to morning_briefing
        assert m.detect_intent("Hello there") == "morning_briefing"

    def test_case_insensitive(self):
        m = _get_app()
        assert m.detect_intent("MORNING BRIEFING") == "morning_briefing"


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


class TestMorningBriefingCard:
    def test_type_is_morning_briefing(self):
        m = _get_app()
        card = m.build_morning_briefing_card("Alice")
        assert card["type"] == "morning_briefing"

    def test_has_title(self):
        m = _get_app()
        card = m.build_morning_briefing_card("Alice")
        assert "title" in card
        assert len(card["title"]) > 0

    def test_title_includes_name(self):
        m = _get_app()
        card = m.build_morning_briefing_card("Alice")
        assert "Alice" in card["title"]

    def test_has_fields(self):
        m = _get_app()
        card = m.build_morning_briefing_card("Alice")
        assert "fields" in card
        assert len(card["fields"]) >= 3

    def test_has_metadata_capability_state(self):
        m = _get_app()
        card = m.build_morning_briefing_card("Alice")
        assert card["metadata"]["capability_state"] == "simulated"

    def test_no_name_fallback(self):
        m = _get_app()
        card = m.build_morning_briefing_card("")
        assert "title" in card


class TestScheduleCard:
    def test_type_is_schedule(self):
        m = _get_app()
        card = m.build_schedule_card([])
        assert card["type"] == "schedule"

    def test_has_title(self):
        m = _get_app()
        card = m.build_schedule_card([])
        assert "title" in card

    def test_has_fields(self):
        m = _get_app()
        items = [{"time": "09:00", "title": "Team standup", "duration": "30m"}]
        card = m.build_schedule_card(items)
        assert len(card["fields"]) >= 1

    def test_field_contains_time_and_title(self):
        m = _get_app()
        items = [{"time": "09:00", "title": "Team standup", "duration": "30m"}]
        card = m.build_schedule_card(items)
        assert "09:00" in card["fields"][0]["label"]
        assert "standup" in card["fields"][0]["value"].lower() or "standup" in card["fields"][0]["label"].lower()

    def test_metadata_capability_simulated(self):
        m = _get_app()
        card = m.build_schedule_card([])
        assert card["metadata"]["capability_state"] == "simulated"

    def test_empty_items_shows_placeholder(self):
        m = _get_app()
        card = m.build_schedule_card([])
        assert len(card["fields"]) >= 1


class TestActionItemsCard:
    def test_type_is_action_items(self):
        m = _get_app()
        card = m.build_action_items_card([])
        assert card["type"] == "action_items"

    def test_has_title(self):
        m = _get_app()
        card = m.build_action_items_card([])
        assert "title" in card

    def test_has_fields(self):
        m = _get_app()
        items = [{"task": "Call dentist", "due": "Today", "priority": "high"}]
        card = m.build_action_items_card(items)
        assert len(card["fields"]) >= 1

    def test_field_has_task_name(self):
        m = _get_app()
        items = [{"task": "Call dentist", "due": "Today", "priority": "high"}]
        card = m.build_action_items_card(items)
        found = any("dentist" in f.get("label", "").lower() or "dentist" in f.get("value", "").lower() for f in card["fields"])
        assert found

    def test_metadata_capability_simulated(self):
        m = _get_app()
        card = m.build_action_items_card([])
        assert card["metadata"]["capability_state"] == "simulated"

    def test_empty_items_shows_placeholder(self):
        m = _get_app()
        card = m.build_action_items_card([])
        assert len(card["fields"]) >= 1


# ---------------------------------------------------------------------------
# Webhook endpoint — morning briefing
# ---------------------------------------------------------------------------


class TestWebhookMorningBriefing:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Good morning! Here's your briefing."):
            resp = client.post("/", json=_webhook_payload("morning briefing"))
        assert resp.status_code == 200

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing text"):
            resp = client.post("/", json=_webhook_payload("morning"))
        assert resp.json()["schema_version"] == "2026-03-01"

    def test_status_completed(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing"):
            resp = client.post("/", json=_webhook_payload("morning"))
        assert resp.json()["status"] == "completed"

    def test_has_content_parts(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing text"):
            resp = client.post("/", json=_webhook_payload("morning"))
        data = resp.json()
        assert len(data["content_parts"]) > 0

    def test_has_morning_briefing_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing"):
            resp = client.post("/", json=_webhook_payload("morning"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "morning_briefing" for c in cards)

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing"):
            resp = client.post("/", json=_webhook_payload("morning briefing"))
        assert len(resp.json().get("actions", [])) > 0

    def test_has_prompt_suggestions_metadata(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing"):
            resp = client.post("/", json=_webhook_payload("morning briefing"))
        suggestions = resp.json().get("metadata", {}).get("prompt_suggestions", [])
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0

    def test_personalisation_display_name(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Good morning!"):
            resp = client.post("/", json=_webhook_payload(
                "morning",
                profile={"display_name": "Mark"},
            ))
        text = resp.json()["content_parts"][0]["text"]
        assert "Mark" in text

    def test_personalisation_name_fallback(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Good morning!"):
            resp = client.post("/", json=_webhook_payload(
                "morning",
                profile={"name": "Alice"},
            ))
        text = resp.json()["content_parts"][0]["text"]
        assert "Alice" in text

    def test_no_name_no_prefix(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="No data"):
            resp = client.post("/", json=_webhook_payload("morning"))
        text = resp.json()["content_parts"][0]["text"]
        assert not text.startswith("Hey ")

    def test_briefing_card_name_in_title(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="briefing"):
            resp = client.post("/", json=_webhook_payload(
                "morning",
                profile={"display_name": "Mark"},
            ))
        cards = resp.json().get("cards", [])
        briefing_cards = [c for c in cards if c["type"] == "morning_briefing"]
        assert any("Mark" in c.get("title", "") for c in briefing_cards)


# ---------------------------------------------------------------------------
# Webhook endpoint — schedule management
# ---------------------------------------------------------------------------


class TestWebhookSchedule:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Schedule updated"):
            resp = client.post("/", json=_webhook_payload("Add a meeting at 3pm"))
        assert resp.status_code == 200

    def test_has_schedule_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Here is your schedule"):
            resp = client.post("/", json=_webhook_payload("What's on my calendar"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "schedule" for c in cards)

    def test_has_actions(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="schedule"):
            resp = client.post("/", json=_webhook_payload("schedule"))
        assert len(resp.json().get("actions", [])) > 0

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("calendar"))
        assert resp.json()["schema_version"] == "2026-03-01"


# ---------------------------------------------------------------------------
# Webhook endpoint — follow-up / reminders
# ---------------------------------------------------------------------------


class TestWebhookFollowUp:
    def test_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Reminder set"):
            resp = client.post("/", json=_webhook_payload("Remind me to call the doctor"))
        assert resp.status_code == 200

    def test_has_action_items_card(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="Action items created"):
            resp = client.post("/", json=_webhook_payload("Set a reminder"))
        cards = resp.json().get("cards", [])
        assert any(c["type"] == "action_items" for c in cards)

    def test_has_actions_with_snooze(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="reminder"):
            resp = client.post("/", json=_webhook_payload("follow up with team"))
        actions = resp.json().get("actions", [])
        labels = [a.get("label", "").lower() for a in actions]
        assert any("snooze" in l or "done" in l or "complete" in l or "remind" in l for l in labels)

    def test_schema_version(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("reminder"))
        assert resp.json()["schema_version"] == "2026-03-01"


# ---------------------------------------------------------------------------
# HMAC signature
# ---------------------------------------------------------------------------


class TestHMACSignature:
    def test_valid_signature_200(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "test-secret")
        body = json.dumps(_webhook_payload("morning"))
        ts = "1700000000"
        sig = _sign("test-secret", ts, body)
        with patch.object(m, "call_llm", return_value="briefing"):
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
        body = json.dumps(_webhook_payload("morning"))
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
        resp = client.post("/", json=_webhook_payload("morning"))
        assert resp.status_code == 401

    def test_no_secret_skips_verification(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("morning"))
        assert resp.status_code == 200


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
                json=_webhook_payload("morning"),
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

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
                json=_webhook_payload("morning"),
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
        assert isinstance(done.get("metadata", {}).get("prompt_suggestions", []), list)

    def test_json_fallback_when_no_accept(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", True)
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post("/", json=_webhook_payload("morning"))
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_stream_disabled_returns_json(self, monkeypatch):
        client = _make_client()
        m = _get_app()
        monkeypatch.setattr(m, "WEBHOOK_SECRET", "")
        monkeypatch.setattr(m, "STREAMING_ENABLED", False)
        with patch.object(m, "call_llm", return_value="ok"):
            resp = client.post(
                "/",
                json=_webhook_payload("morning"),
                headers={"Accept": "text/event-stream"},
            )
        assert resp.headers.get("content-type", "").startswith("application/json")


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
