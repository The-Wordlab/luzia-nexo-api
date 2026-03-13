"""Tests for the travel-planning RAG webhook partner (python/ variant).

All tests use monkeypatching and mocks to avoid requiring a live vector store,
RSS feeds, or an LLM API key.

Coverage:
  - Intent detection (unit)
  - Destination card shape and field validation (unit)
  - Itinerary card shape (unit)
  - Ingest helpers: format_destination_text (unit)
  - Webhook endpoint: destination, itinerary, budget, weather, empty, personalisation (integration)
  - HMAC signature: valid, invalid, missing when secret is set (integration)
  - SSE streaming path (integration)
  - POST /ingest endpoint (integration)
  - GET /health endpoint (integration)
  - Empty query handling (integration)
  - Seed data completeness (unit)
  - No-results graceful fallback (integration)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[3]))

from test_support.fake_vector_store import FakeVectorStoreRegistry

import ingest as _ingest_module
import server as _server_module
from ingest import SEED_DESTINATIONS, format_destination_text
from server import (
    app,
    build_itinerary_card,
    destination_to_card,
    detect_intent,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_client(monkeypatch) -> TestClient:
    """Return a test client with startup hooks stubbed out."""
    fake_store = FakeVectorStoreRegistry()

    def _noop_seed_destinations():
        pass

    async def _noop_crawl_feeds(_feeds=None):
        return 0

    monkeypatch.setattr(_ingest_module, "seed_destinations", _noop_seed_destinations)
    monkeypatch.setattr(_server_module, "seed_destinations", _noop_seed_destinations)
    monkeypatch.setattr(_ingest_module, "crawl_feeds", _noop_crawl_feeds)
    monkeypatch.setattr(_ingest_module, "get_collection", fake_store.get)
    monkeypatch.setattr(_server_module, "get_collection", fake_store.get)

    return TestClient(app)


def _sign(secret: str, timestamp: str, body: str) -> str:
    """Produce a valid sha256 HMAC signature."""
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


_SAMPLE_DEST = SEED_DESTINATIONS[0]  # Paris


def _sample_dest_result() -> dict[str, Any]:
    """Return a destination dict as it would come back from vector search."""
    return {
        **{k: v for k, v in _SAMPLE_DEST.items() if k != "description"},
        "text": format_destination_text(_SAMPLE_DEST),
        "distance": 0.05,
        "tags": ", ".join(_SAMPLE_DEST["tags"]),
    }


_SAMPLE_ARTICLE = {
    "text": "Top 10 things to do in Paris this spring.",
    "title": "Paris Spring Guide",
    "link": "https://example.com/paris-spring",
    "published": "March 1, 2026",
    "excerpt": "Top 10 things to do in Paris this spring.",
    "distance": 0.1,
}


# ---------------------------------------------------------------------------
# Unit: intent detection
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_destination_keywords(self) -> None:
        assert detect_intent("Where should I travel in Europe?") == "destination"
        assert detect_intent("Recommend a place to visit") == "destination"
        assert detect_intent("Best destinations to discover") == "destination"

    def test_itinerary_keywords(self) -> None:
        assert detect_intent("Plan a 3-day itinerary in Tokyo") == "itinerary"
        assert detect_intent("What to do in Paris for a week?") == "itinerary"
        assert detect_intent("Create a 5-day schedule for Barcelona") == "itinerary"

    def test_budget_keywords(self) -> None:
        assert detect_intent("How much does it cost to visit Bali?") == "budget"
        assert detect_intent("Cheap places to travel in Asia") == "budget"
        assert detect_intent("Budget travel tips for backpackers") == "budget"

    def test_weather_keywords(self) -> None:
        assert detect_intent("What is the best time to visit Japan?") == "weather"
        assert detect_intent("When does the monsoon season start in Bali?") == "weather"
        assert detect_intent("Climate in Iceland during winter") == "weather"

    def test_empty_string_returns_known_intent(self) -> None:
        result = detect_intent("")
        assert result in ("destination", "itinerary", "budget", "weather")

    def test_no_keywords_defaults_to_destination(self) -> None:
        assert detect_intent("Tell me something interesting") == "destination"


# ---------------------------------------------------------------------------
# Unit: destination card shape
# ---------------------------------------------------------------------------


class TestDestinationCard:
    def test_card_type(self) -> None:
        card = destination_to_card(_sample_dest_result())
        assert card["type"] == "destination"

    def test_card_title_contains_city_and_country(self) -> None:
        card = destination_to_card(_sample_dest_result())
        assert "Paris" in card["title"]
        assert "France" in card["title"]

    def test_card_subtitle_is_region(self) -> None:
        card = destination_to_card(_sample_dest_result())
        assert card["subtitle"] == "Western Europe"

    def test_card_has_required_fields(self) -> None:
        card = destination_to_card(_sample_dest_result())
        labels = [f["label"] for f in card["fields"]]
        assert "Best time" in labels
        assert "Budget" in labels
        assert "Language" in labels
        assert "Currency" in labels

    def test_card_badges_present(self) -> None:
        card = destination_to_card(_sample_dest_result())
        assert len(card["badges"]) >= 1

    def test_card_capability_state(self) -> None:
        card = destination_to_card(_sample_dest_result())
        assert card["metadata"]["capability_state"] == "live"

    def test_card_description_present(self) -> None:
        card = destination_to_card(_sample_dest_result())
        assert len(card["description"]) > 0


# ---------------------------------------------------------------------------
# Unit: itinerary card shape
# ---------------------------------------------------------------------------


class TestItineraryCard:
    def test_card_type(self) -> None:
        card = build_itinerary_card(_sample_dest_result(), days=3)
        assert card["type"] == "itinerary"

    def test_card_title_contains_days_and_city(self) -> None:
        card = build_itinerary_card(_sample_dest_result(), days=3)
        assert "3" in card["title"]
        assert "Paris" in card["title"]

    def test_card_fields_count_equals_days(self) -> None:
        for days in [2, 3, 5]:
            card = build_itinerary_card(_sample_dest_result(), days=days)
            assert len(card["fields"]) == days

    def test_card_field_labels_are_day_numbers(self) -> None:
        card = build_itinerary_card(_sample_dest_result(), days=3)
        labels = [f["label"] for f in card["fields"]]
        assert "Day 1" in labels
        assert "Day 2" in labels
        assert "Day 3" in labels

    def test_card_badges_include_day_count(self) -> None:
        card = build_itinerary_card(_sample_dest_result(), days=4)
        badge_text = " ".join(card["badges"])
        assert "4" in badge_text


# ---------------------------------------------------------------------------
# Unit: format_destination_text
# ---------------------------------------------------------------------------


class TestFormatDestinationText:
    def test_contains_city(self) -> None:
        text = format_destination_text(_SAMPLE_DEST)
        assert "Paris" in text

    def test_contains_country(self) -> None:
        text = format_destination_text(_SAMPLE_DEST)
        assert "France" in text

    def test_contains_highlights(self) -> None:
        text = format_destination_text(_SAMPLE_DEST)
        assert "Eiffel Tower" in text

    def test_contains_budget(self) -> None:
        text = format_destination_text(_SAMPLE_DEST)
        assert "$" in text

    def test_contains_language(self) -> None:
        text = format_destination_text(_SAMPLE_DEST)
        assert "French" in text


# ---------------------------------------------------------------------------
# Integration: webhook contract compliance
# ---------------------------------------------------------------------------


class TestWebhookContract:
    def test_response_has_schema_version(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Paris is wonderful."):
            data = client.post("/", json={"message": {"content": "tell me about Paris"}}).json()
        assert data["schema_version"] == "2026-03-01"
        assert data["task"]["status"] == "completed"
        assert data["capability"]["name"] == "travel.rag"
        assert isinstance(data["artifacts"], list)

    def test_response_has_status_completed(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Paris is wonderful."):
            data = client.post("/", json={"message": {"content": "Paris"}}).json()
        assert data["status"] == "completed"

    def test_response_has_content_parts(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Paris is wonderful."):
            data = client.post("/", json={"message": {"content": "Paris"}}).json()
        assert len(data["content_parts"]) >= 1
        assert data["content_parts"][0]["type"] == "text"

    def test_response_has_cards_list(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            data = client.post("/", json={"message": {"content": "Paris"}}).json()
        assert isinstance(data["cards"], list)

    def test_response_has_actions_list(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            data = client.post("/", json={"message": {"content": "Paris"}}).json()
        assert isinstance(data["actions"], list)


# ---------------------------------------------------------------------------
# Integration: destination intent
# ---------------------------------------------------------------------------


class TestWebhookDestination:
    def test_destination_card_type(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Paris is a wonderful destination."):
            data = client.post("/", json={"message": {"content": "Where should I visit in Europe?"}}).json()
        assert len(data["cards"]) >= 1
        assert data["cards"][0]["type"] == "destination"

    def test_destination_card_fields_present(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            data = client.post("/", json={"message": {"content": "Recommend a destination"}}).json()
        card = data["cards"][0]
        labels = [f["label"] for f in card["fields"]]
        assert "Best time" in labels
        assert "Budget" in labels

    def test_destination_actions_include_map_link(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            data = client.post("/", json={"message": {"content": "Where to visit"}}).json()
        labels = [a["label"].lower() for a in data["actions"]]
        assert any("map" in lbl or "view" in lbl for lbl in labels)

    def test_destination_actions_include_flights_link(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            data = client.post("/", json={"message": {"content": "travel destination"}}).json()
        labels = [a["label"].lower() for a in data["actions"]]
        assert any("flight" in lbl for lbl in labels)


# ---------------------------------------------------------------------------
# Integration: itinerary intent
# ---------------------------------------------------------------------------


class TestWebhookItinerary:
    def test_itinerary_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "call_llm", return_value="Day 1: Eiffel Tower."):
            resp = client.post("/", json={"message": {"content": "Plan a 3-day itinerary in Paris"}})
        assert resp.status_code == 200

    def test_itinerary_includes_itinerary_card(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "call_llm", return_value="Day 1: Eiffel Tower."):
            data = client.post("/", json={"message": {"content": "3-day itinerary for Paris"}}).json()
        card_types = [c["type"] for c in data["cards"]]
        assert "itinerary" in card_types

    def test_itinerary_day_count_parsed_from_query(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            data = client.post("/", json={"message": {"content": "5-day itinerary for Tokyo"}}).json()
        itinerary_cards = [c for c in data["cards"] if c["type"] == "itinerary"]
        assert len(itinerary_cards) >= 1
        assert len(itinerary_cards[0]["fields"]) == 5


# ---------------------------------------------------------------------------
# Integration: budget intent
# ---------------------------------------------------------------------------


class TestWebhookBudget:
    def test_budget_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Bali costs $50-150/day."):
            resp = client.post("/", json={"message": {"content": "How much does Bali cost?"}})
        assert resp.status_code == 200

    def test_budget_response_has_destination_cards(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Budget info."):
            data = client.post("/", json={"message": {"content": "cheap places to travel"}}).json()
        assert len(data["cards"]) >= 1
        assert data["cards"][0]["type"] == "destination"


# ---------------------------------------------------------------------------
# Integration: weather intent
# ---------------------------------------------------------------------------


class TestWebhookWeather:
    def test_weather_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Best time is April-June."):
            resp = client.post("/", json={"message": {"content": "Best time to visit Paris?"}})
        assert resp.status_code == 200

    def test_weather_response_has_destination_card(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Climate info."):
            data = client.post("/", json={"message": {"content": "when is dry season in Bali?"}}).json()
        assert len(data["cards"]) >= 1


# ---------------------------------------------------------------------------
# Integration: empty message
# ---------------------------------------------------------------------------


class TestWebhookEmpty:
    def test_empty_message_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        resp = client.post("/", json={"message": {"content": ""}})
        assert resp.status_code == 200

    def test_empty_message_has_valid_envelope(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        data = client.post("/", json={"message": {"content": ""}}).json()
        assert data["schema_version"] == "2026-03-01"
        assert data["status"] == "completed"
        assert len(data["content_parts"]) >= 1

    def test_missing_message_key_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        data = client.post("/", json={}).json()
        assert data["status"] == "completed"

    def test_empty_message_prompts_for_travel_query(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        data = client.post("/", json={"message": {"content": ""}}).json()
        text = data["content_parts"][0]["text"].lower()
        assert "travel" in text or "destination" in text or "itinerary" in text


# ---------------------------------------------------------------------------
# Integration: personalisation
# ---------------------------------------------------------------------------


class TestPersonalisation:
    def test_display_name_prepended(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Paris is beautiful."):
            data = client.post(
                "/",
                json={"message": {"content": "Tell me about Paris"}, "profile": {"display_name": "Alice"}},
            ).json()
        assert data["content_parts"][0]["text"].startswith("Hey Alice!")

    def test_name_field_used_when_no_display_name(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Tokyo is amazing."):
            data = client.post(
                "/",
                json={"message": {"content": "Tell me about Tokyo"}, "profile": {"name": "Bob"}},
            ).json()
        assert data["content_parts"][0]["text"].startswith("Hey Bob!")

    def test_no_name_no_prefix(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Paris is great."):
            data = client.post("/", json={"message": {"content": "Paris"}}).json()
        assert not data["content_parts"][0]["text"].startswith("Hey")


# ---------------------------------------------------------------------------
# Integration: HMAC signature validation
# ---------------------------------------------------------------------------


class TestHMACSignature:
    def test_no_secret_passes_without_header(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "WEBHOOK_SECRET", "")
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            resp = client.post("/", json={"message": {"content": "Paris"}})
        assert resp.status_code == 200

    def test_valid_signature_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "WEBHOOK_SECRET", "test-secret")
        body = '{"message":{"content":"Paris"}}'
        ts = "1700000000"
        sig = _sign("test-secret", ts, body)
        with patch.object(_server_module, "search_destinations", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            resp = client.post(
                "/",
                data=body,
                headers={"Content-Type": "application/json", "x-timestamp": ts, "x-signature": sig},
            )
        assert resp.status_code == 200

    def test_invalid_signature_returns_401(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "WEBHOOK_SECRET", "test-secret")
        body = '{"message":{"content":"Paris"}}'
        resp = client.post(
            "/",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-timestamp": "1700000000",
                "x-signature": "sha256=badhash",
            },
        )
        assert resp.status_code == 401

    def test_missing_signature_header_returns_401(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "WEBHOOK_SECRET", "test-secret")
        body = '{"message":{"content":"Paris"}}'
        resp = client.post("/", data=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration: SSE streaming
# ---------------------------------------------------------------------------


class TestSSEStreaming:
    def test_sse_stream_returned_when_accept_and_enabled(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", True)

        async def _fake_stream_llm(_system, _user):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'Paris'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "stream_llm", new=_fake_stream_llm):
            resp = client.post(
                "/",
                json={"message": {"content": "Tell me about Paris"}},
                headers={"Accept": "text/event-stream"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "Paris" in resp.text
        assert "event: task.started" in resp.text
        assert "event: task.delta" in resp.text
        assert "event: done" in resp.text

    def test_sse_done_event_has_cards_and_actions(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", True)

        async def _fake_stream_llm(_system, _user):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'ok'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "stream_llm", new=_fake_stream_llm):
            resp = client.post(
                "/",
                json={"message": {"content": "Paris"}},
                headers={"Accept": "text/event-stream"},
            )

        captured_events = []
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                event = json.loads(line[len("data:"):].strip())
                captured_events.append(event)

        done_events = [e for e in captured_events if e.get("type") == "done"]
        assert len(done_events) >= 1
        done = done_events[-1]
        assert "cards" in done
        assert "actions" in done
        assert done["schema_version"] == "2026-03-01"
        assert done["status"] == "completed"
        assert done["capability"]["name"] == "travel.rag"
        assert isinstance(done["artifacts"], list)

    def test_json_response_when_no_accept_header(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", True)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            resp = client.post("/", json={"message": {"content": "Paris"}})
        assert resp.status_code == 200
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    def test_json_response_when_streaming_disabled(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", False)
        with patch.object(_server_module, "search_destinations", return_value=[_sample_dest_result()]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            resp = client.post(
                "/",
                json={"message": {"content": "Paris"}},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" not in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Integration: POST /ingest endpoint
# ---------------------------------------------------------------------------


class TestIngestEndpoint:
    def test_ingest_returns_ok(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        summary = {"destination_profiles": 12, "article_chunks": 45}

        async def _fake_full(**_kwargs):
            return summary

        monkeypatch.setattr(_server_module, "run_full_ingest", _fake_full)
        resp = client.post("/ingest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["summary"]["destination_profiles"] == 12
        assert data["summary"]["article_chunks"] == 45
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# Integration: GET /health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_ok(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_col = MagicMock()
        mock_col.count.return_value = 12

        with patch.object(_server_module, "get_collection", return_value=mock_col):
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_returns_collection_counts(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_col = MagicMock()
        mock_col.count.return_value = 12

        with patch.object(_server_module, "get_collection", return_value=mock_col):
            data = client.get("/health").json()

        assert "destinations" in data["collections"]
        assert "travel_articles" in data["collections"]

    def test_health_includes_model_info(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_col = MagicMock()
        mock_col.count.return_value = 0

        with patch.object(_server_module, "get_collection", return_value=mock_col):
            data = client.get("/health").json()

        assert "llm_model" in data
        assert "embedding_model" in data
        assert "streaming_enabled" in data
        assert "vector_store" in data
        assert "backend" in data["vector_store"]
        assert "durable" in data["vector_store"]

    def test_vector_store_metadata_pgvector_is_durable(self, monkeypatch) -> None:
        monkeypatch.setattr(_server_module, "VECTOR_STORE_BACKEND", "pgvector")
        data = _server_module._vector_store_metadata()
        assert data["backend"] == "pgvector"
        assert data["durable"] is True

    def test_pgvector_backend_requires_dsn(self, monkeypatch) -> None:
        monkeypatch.setattr(_ingest_module, "VECTOR_STORE_BACKEND", "pgvector")
        monkeypatch.setattr(_ingest_module, "PGVECTOR_DSN", "")
        monkeypatch.setattr(_ingest_module, "_pg_conn", None)
        _ingest_module.reset_client()

        collection = _ingest_module.get_collection(_ingest_module.COLLECTION_DESTINATIONS)
        with pytest.raises(RuntimeError, match="(PGVECTOR_DSN is required|psycopg is required)"):
            collection.count()


class TestAgentCard:
    def test_agent_card_has_capability(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "nexo-travel-rag"
        assert data["capabilities"]["items"][0]["name"] == "travel.rag"


# ---------------------------------------------------------------------------
# Unit: seed data completeness
# ---------------------------------------------------------------------------


class TestSeedData:
    def test_seed_destinations_minimum_count(self) -> None:
        assert len(SEED_DESTINATIONS) >= 10

    def test_seed_destinations_have_required_fields(self) -> None:
        required = {
            "id", "city", "country", "region", "description",
            "highlights", "best_time", "budget_range", "language", "currency", "tags",
        }
        for dest in SEED_DESTINATIONS:
            missing = required - set(dest.keys())
            assert not missing, f"Destination {dest.get('city')} missing: {missing}"

    def test_seed_destinations_ids_are_unique(self) -> None:
        ids = [d["id"] for d in SEED_DESTINATIONS]
        assert len(ids) == len(set(ids))

    def test_seed_destinations_cover_multiple_regions(self) -> None:
        regions = {d["region"] for d in SEED_DESTINATIONS}
        assert len(regions) >= 4

    def test_seed_destinations_have_non_empty_descriptions(self) -> None:
        for dest in SEED_DESTINATIONS:
            assert len(dest["description"]) > 100, f"{dest['city']} description too short"

    def test_seed_destinations_have_tags_list(self) -> None:
        for dest in SEED_DESTINATIONS:
            assert isinstance(dest["tags"], list)
            assert len(dest["tags"]) >= 3


# ---------------------------------------------------------------------------
# Integration: no-results graceful fallback
# ---------------------------------------------------------------------------


class TestNoResultsFallback:
    def test_no_results_returns_completed_status(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]):
            data = client.post("/", json={"message": {"content": "obscure query"}}).json()
        assert data["status"] == "completed"
        assert len(data["content_parts"]) >= 1

    def test_no_results_personalised(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]):
            data = client.post(
                "/",
                json={"message": {"content": "obscure query"}, "profile": {"display_name": "Sam"}},
            ).json()
        assert data["content_parts"][0]["text"].startswith("Hey Sam!")

    def test_no_results_has_empty_cards_and_actions(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_destinations", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]):
            data = client.post("/", json={"message": {"content": "obscure query"}}).json()
        assert data["cards"] == []
        assert data["actions"] == []
