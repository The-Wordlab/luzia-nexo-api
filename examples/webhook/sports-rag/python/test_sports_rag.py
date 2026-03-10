"""Tests for the sports-feed RAG webhook partner (python/ variant).

All tests use monkeypatching and mocks to avoid requiring a running ChromaDB
instance, live RSS feeds, or an LLM API key.

Coverage:
  - Intent detection (unit)
  - Match/card formatting (unit)
  - Ingest helpers: format_match_text, format_standings_text (unit)
  - Webhook endpoint: scores, standings, news, empty, personalisation (integration)
  - HMAC signature: valid, invalid, missing when secret is set (integration)
  - SSE streaming path (integration)
  - POST /ingest and POST /ingest/live endpoints (integration)
  - Admin endpoints: GET /admin/status, POST /admin/refresh (integration)
  - Seed data completeness and ordering (unit)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import ingest as _ingest_module
import server as _server_module
from ingest import (
    SEED_MATCHES,
    SEED_STANDINGS,
    format_match_text,
    format_standings_text,
)
from server import (
    app,
    build_standings_card,
    detect_intent,
    match_to_card,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_client(monkeypatch) -> TestClient:
    """Return a test client with startup hooks stubbed out."""

    def _noop_seed_matches():
        pass

    def _noop_seed_standings():
        pass

    async def _noop_crawl_feeds(_feeds=None):
        return 0

    monkeypatch.setattr(_ingest_module, "seed_matches", _noop_seed_matches)
    monkeypatch.setattr(_ingest_module, "seed_standings", _noop_seed_standings)
    monkeypatch.setattr(_server_module, "seed_matches", _noop_seed_matches)
    monkeypatch.setattr(_server_module, "seed_standings", _noop_seed_standings)
    monkeypatch.setattr(_ingest_module, "crawl_feeds", _noop_crawl_feeds)

    return TestClient(app)


def _sign(secret: str, timestamp: str, body: str) -> str:
    """Produce a valid sha256 HMAC signature."""
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


_SAMPLE_MATCH = SEED_MATCHES[0]  # Arsenal 3-1 Chelsea


def _sample_match_result() -> dict[str, Any]:
    return {
        **_SAMPLE_MATCH,
        "text": format_match_text(_SAMPLE_MATCH),
        "distance": 0.05,
    }


# ---------------------------------------------------------------------------
# Unit: intent detection
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_scores_keywords(self) -> None:
        assert detect_intent("What was the score?") == "scores"
        assert detect_intent("Did Arsenal win?") == "scores"
        assert detect_intent("Match result this weekend") == "scores"
        assert detect_intent("Liverpool goal scorers") == "scores"

    def test_standings_keywords(self) -> None:
        assert detect_intent("Who is top of the Premier League table?") == "standings"
        assert detect_intent("Show me the standings") == "standings"
        assert detect_intent("What position is Arsenal in the rankings?") == "standings"

    def test_news_keywords(self) -> None:
        assert detect_intent("Any transfer news for Haaland?") == "news"
        assert detect_intent("Latest injury updates") == "news"
        assert detect_intent("Preview of the Champions League final") == "news"

    def test_ambiguous_defaults_to_scores(self) -> None:
        # A single score keyword and no others should resolve to "scores"
        assert detect_intent("goal") == "scores"

    def test_empty_string_returns_known_intent(self) -> None:
        result = detect_intent("")
        assert result in ("scores", "news", "standings")


# ---------------------------------------------------------------------------
# Unit: match and card formatting
# ---------------------------------------------------------------------------


class TestMatchFormatting:
    def test_format_match_text_contains_teams(self) -> None:
        text = format_match_text(_SAMPLE_MATCH)
        assert "Arsenal" in text
        assert "Chelsea" in text

    def test_format_match_text_contains_score(self) -> None:
        text = format_match_text(_SAMPLE_MATCH)
        assert "3-1" in text

    def test_format_match_text_contains_competition(self) -> None:
        text = format_match_text(_SAMPLE_MATCH)
        assert "Premier League" in text

    def test_format_match_text_contains_goals(self) -> None:
        text = format_match_text(_SAMPLE_MATCH)
        assert "Saka" in text

    def test_match_to_card_type(self) -> None:
        card = match_to_card(_sample_match_result())
        assert card["type"] == "match_result"

    def test_match_to_card_title_contains_teams(self) -> None:
        card = match_to_card(_sample_match_result())
        assert "Arsenal" in card["title"]
        assert "Chelsea" in card["title"]

    def test_match_to_card_subtitle_contains_competition(self) -> None:
        card = match_to_card(_sample_match_result())
        assert "Premier League" in card["subtitle"]

    def test_match_to_card_badges(self) -> None:
        card = match_to_card(_sample_match_result())
        assert "Full Time" in card["badges"]
        assert "Premier League" in card["badges"]

    def test_match_to_card_fields_date_venue(self) -> None:
        card = match_to_card(_sample_match_result())
        labels = [f["label"] for f in card["fields"]]
        assert "Date" in labels
        assert "Venue" in labels

    def test_match_to_card_capability_state(self) -> None:
        card = match_to_card(_sample_match_result())
        assert card["metadata"]["capability_state"] == "live"


class TestStandingsFormatting:
    def test_format_standings_text_contains_competition(self) -> None:
        text = format_standings_text(SEED_STANDINGS[:3], "Premier League")
        assert "Premier League" in text

    def test_format_standings_text_contains_team_names(self) -> None:
        text = format_standings_text(SEED_STANDINGS[:3], "Premier League")
        assert "Arsenal" in text
        assert "Liverpool" in text

    def test_build_standings_card_type(self) -> None:
        card = build_standings_card(SEED_STANDINGS, "Premier League", "Test Label")
        assert card["type"] == "standings_table"

    def test_build_standings_card_title(self) -> None:
        card = build_standings_card(SEED_STANDINGS, "Premier League", "Test Label")
        assert "Premier League" in card["title"]

    def test_build_standings_card_top_5_fields(self) -> None:
        card = build_standings_card(SEED_STANDINGS, "Premier League", "Test Label")
        assert len(card["fields"]) == 5
        first_field = card["fields"][0]
        assert "Arsenal" in first_field["label"]
        assert "pts" in first_field["value"]


# ---------------------------------------------------------------------------
# Integration: webhook endpoint - scores intent
# ---------------------------------------------------------------------------


class TestWebhookScores:
    def test_scores_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal beat Chelsea 3-1."):
            resp = client.post("/", json={"message": {"content": "Arsenal score this weekend"}})
        assert resp.status_code == 200

    def test_scores_response_envelope_fields(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal beat Chelsea 3-1."):
            data = client.post("/", json={"message": {"content": "Arsenal score"}}).json()

        assert data["schema_version"] == "2026-03-01"
        assert data["status"] == "completed"
        assert data["content_parts"][0]["text"] == "Arsenal beat Chelsea 3-1."

    def test_scores_cards_are_match_result_type(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Result."):
            data = client.post("/", json={"message": {"content": "What was the result?"}}).json()

        assert len(data["cards"]) >= 1
        assert data["cards"][0]["type"] == "match_result"
        assert "Arsenal" in data["cards"][0]["title"]

    def test_scores_actions_contain_view_match_details(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Result."):
            data = client.post("/", json={"message": {"content": "Arsenal match result"}}).json()

        assert len(data["actions"]) >= 1
        action = data["actions"][0]
        assert "label" in action
        assert "url" in action
        assert "Arsenal" in action["label"]

    def test_scores_actions_have_view_match_details_label(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Result."):
            data = client.post("/", json={"message": {"content": "Arsenal result"}}).json()

        labels = [a["label"] for a in data["actions"]]
        assert any("match details" in lbl.lower() or "View" in lbl for lbl in labels)


# ---------------------------------------------------------------------------
# Integration: webhook endpoint - standings intent
# ---------------------------------------------------------------------------


class TestWebhookStandings:
    def test_standings_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_standings", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal lead the table."):
            resp = client.post("/", json={"message": {"content": "Who is top of the table?"}})
        assert resp.status_code == 200

    def test_standings_card_is_standings_table_type(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_standings = [{"text": "Premier League Standings:\n1. Arsenal: P28 W20 D5 L3 GD+42 Pts65", "competition": "Premier League", "date": "2026-03-05", "top_team": "Arsenal"}]
        with patch.object(_server_module, "search_standings", return_value=mock_standings), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal lead with 65 pts."):
            data = client.post("/", json={"message": {"content": "Premier League standings"}}).json()

        assert len(data["cards"]) >= 1
        assert data["cards"][0]["type"] == "standings_table"
        assert "Premier League" in data["cards"][0]["title"]

    def test_standings_actions_contain_see_full_standings(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_standings = [{"text": "Premier League Standings:\n1. Arsenal", "competition": "Premier League", "date": "2026-03-05", "top_team": "Arsenal"}]
        with patch.object(_server_module, "search_standings", return_value=mock_standings), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "call_llm", return_value="Top of the table."):
            data = client.post("/", json={"message": {"content": "league table"}}).json()

        assert len(data["actions"]) >= 1
        labels = [a["label"].lower() for a in data["actions"]]
        assert any("standings" in lbl for lbl in labels)


# ---------------------------------------------------------------------------
# Integration: webhook endpoint - news intent
# ---------------------------------------------------------------------------


class TestWebhookNews:
    def test_news_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        sample_articles = [
            {
                "text": "Arsenal sign new striker.",
                "title": "Arsenal Transfer News",
                "link": "https://example.com/arsenal-transfer",
                "published": "March 5, 2026",
                "excerpt": "Arsenal sign new striker.",
                "distance": 0.1,
            }
        ]
        with patch.object(_server_module, "search_articles", return_value=sample_articles), \
             patch.object(_server_module, "call_llm", return_value="Arsenal active in transfer market."):
            resp = client.post("/", json={"message": {"content": "Any transfer news?"}})
        assert resp.status_code == 200

    def test_news_card_is_news_article_type(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        sample_articles = [
            {
                "text": "Haaland injury update.",
                "title": "Haaland Injury Update",
                "link": "https://example.com/haaland",
                "published": "March 6, 2026",
                "excerpt": "Haaland injury update.",
                "distance": 0.2,
            }
        ]
        with patch.object(_server_module, "search_articles", return_value=sample_articles), \
             patch.object(_server_module, "call_llm", return_value="Haaland is recovering."):
            data = client.post("/", json={"message": {"content": "Latest injury news"}}).json()

        assert len(data["cards"]) >= 1
        assert data["cards"][0]["type"] == "news_article"

    def test_news_actions_link_to_articles(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        sample_articles = [
            {
                "text": "Transfer window update.",
                "title": "Transfer Update",
                "link": "https://example.com/transfer",
                "published": "March 7, 2026",
                "excerpt": "Transfer window update.",
                "distance": 0.15,
            }
        ]
        with patch.object(_server_module, "search_articles", return_value=sample_articles), \
             patch.object(_server_module, "call_llm", return_value="Active transfer market."):
            data = client.post("/", json={"message": {"content": "transfer news"}}).json()

        assert len(data["actions"]) >= 1
        assert data["actions"][0]["url"] == "https://example.com/transfer"


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


# ---------------------------------------------------------------------------
# Integration: personalisation
# ---------------------------------------------------------------------------


class TestPersonalisation:
    def test_display_name_prepended(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal won."):
            data = client.post(
                "/",
                json={"message": {"content": "Arsenal result"}, "profile": {"display_name": "Alex"}},
            ).json()
        assert data["content_parts"][0]["text"].startswith("Hey Alex!")

    def test_name_field_used_when_no_display_name(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal won."):
            data = client.post(
                "/",
                json={"message": {"content": "Arsenal result"}, "profile": {"name": "Jordan"}},
            ).json()
        assert data["content_parts"][0]["text"].startswith("Hey Jordan!")

    def test_no_name_no_prefix(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal won."):
            data = client.post("/", json={"message": {"content": "Arsenal result"}}).json()
        assert not data["content_parts"][0]["text"].startswith("Hey")


# ---------------------------------------------------------------------------
# Integration: HMAC signature
# ---------------------------------------------------------------------------


class TestHMACSignature:
    def test_no_secret_passes_without_header(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "WEBHOOK_SECRET", "")
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="ok"):
            resp = client.post("/", json={"message": {"content": "score"}})
        assert resp.status_code == 200

    def test_valid_signature_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "WEBHOOK_SECRET", "test-secret")
        body = '{"message":{"content":"score"}}'
        ts = "1700000000"
        sig = _sign("test-secret", ts, body)
        with patch.object(_server_module, "search_matches", return_value=[]), \
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
        body = '{"message":{"content":"score"}}'
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
        body = '{"message":{"content":"score"}}'
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
            yield f"data: {json.dumps({'type': 'delta', 'text': 'Arsenal'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "stream_llm", new=_fake_stream_llm):
            resp = client.post(
                "/",
                json={"message": {"content": "Arsenal score"}},
                headers={"Accept": "text/event-stream"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "Arsenal" in resp.text

    def test_sse_done_event_has_cards_and_actions(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", True)

        async def _fake_stream_llm(_system, _user):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'ok'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "stream_llm", new=_fake_stream_llm):
            resp = client.post(
                "/",
                json={"message": {"content": "score"}},
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

    def test_json_response_when_no_accept_header(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", True)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal won."):
            resp = client.post("/", json={"message": {"content": "score"}})
        assert resp.status_code == 200
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    def test_json_response_when_streaming_disabled(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "STREAMING_ENABLED", False)
        with patch.object(_server_module, "search_matches", return_value=[_sample_match_result()]), \
             patch.object(_server_module, "call_llm", return_value="Arsenal won."):
            resp = client.post(
                "/",
                json={"message": {"content": "score"}},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" not in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Integration: ingest endpoints
# ---------------------------------------------------------------------------


class TestIngestEndpoints:
    def test_post_ingest_returns_summary(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        summary = {"article_chunks": 10, "match_records": 10, "standings_docs": 1}

        async def _fake_full(**_kwargs):
            return summary

        monkeypatch.setattr(_server_module, "run_full_ingest", _fake_full)
        resp = client.post("/ingest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["summary"]["article_chunks"] == 10
        assert data["summary"]["match_records"] == 10
        assert "timestamp" in data

    def test_post_ingest_live_returns_summary(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        summary = {"match_records_updated": 5, "standings_docs_updated": 1}

        async def _fake_live(**_kwargs):
            return summary

        monkeypatch.setattr(_server_module, "run_live_ingest", _fake_live)
        resp = client.post("/ingest/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["summary"]["match_records_updated"] == 5
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# Integration: health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_includes_vector_store_metadata(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_col = MagicMock()
        mock_col.count.return_value = 7

        with patch.object(_server_module, "get_collection", return_value=mock_col):
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "collections" in data
        assert "vector_store" in data
        assert "backend" in data["vector_store"]
        assert "durable" in data["vector_store"]


# ---------------------------------------------------------------------------
# Integration: admin endpoints
# ---------------------------------------------------------------------------


class TestAdminEndpoints:
    def test_admin_status_structure(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_col = MagicMock()
        mock_col.count.return_value = 7

        with patch.object(_server_module, "get_collection", return_value=mock_col):
            resp = client.get("/admin/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["collections"]["articles"]["count"] == 7
        assert data["collections"]["match_results"]["count"] == 7
        assert data["collections"]["standings"]["count"] == 7
        assert "llm_model" in data["config"]
        assert "feeds" in data["config"]
        assert "streaming_enabled" in data["config"]
        assert "football_data_api_configured" in data["config"]
        assert "timestamp" in data

    def test_admin_refresh_queues_ingest(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)

        async def _noop(**_kwargs):
            return {}

        with patch.object(_server_module, "run_full_ingest", _noop):
            resp = client.post("/admin/refresh")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refresh_scheduled"


# ---------------------------------------------------------------------------
# Unit: seed data completeness
# ---------------------------------------------------------------------------


class TestSeedData:
    def test_seed_matches_have_required_fields(self) -> None:
        required = {"id", "home_team", "away_team", "home_score", "away_score", "competition", "date", "goals"}
        for match in SEED_MATCHES:
            missing = required - set(match.keys())
            assert not missing, f"Match {match.get('id')} missing: {missing}"

    def test_seed_standings_have_required_fields(self) -> None:
        required = {"position", "team", "played", "won", "drawn", "lost", "gd", "points"}
        for entry in SEED_STANDINGS:
            missing = required - set(entry.keys())
            assert not missing, f"Standing {entry.get('team')} missing: {missing}"

    def test_seed_standings_ordered_by_position(self) -> None:
        positions = [s["position"] for s in SEED_STANDINGS]
        assert positions == sorted(positions)

    def test_seed_matches_minimum_count(self) -> None:
        assert len(SEED_MATCHES) >= 10

    def test_seed_matches_cover_multiple_competitions(self) -> None:
        competitions = {m["competition"] for m in SEED_MATCHES}
        assert len(competitions) >= 3


# ---------------------------------------------------------------------------
# Unit: no-results graceful fallback
# ---------------------------------------------------------------------------


class TestNoResultsFallback:
    def test_no_results_returns_completed_status(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "search_standings", return_value=[]):
            data = client.post("/", json={"message": {"content": "score"}}).json()
        assert data["status"] == "completed"
        assert len(data["content_parts"]) >= 1

    def test_no_results_personalised(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        with patch.object(_server_module, "search_matches", return_value=[]), \
             patch.object(_server_module, "search_articles", return_value=[]), \
             patch.object(_server_module, "search_standings", return_value=[]):
            data = client.post(
                "/",
                json={"message": {"content": "score"}, "profile": {"display_name": "Sam"}},
            ).json()
        assert data["content_parts"][0]["text"].startswith("Hey Sam!")
