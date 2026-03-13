"""Tests for football-live webhook — ~65 TDD tests, all mocked (no API key needed)."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[3]))

from test_support.fake_vector_store import FakeVectorStoreRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Defer heavy imports so monkeypatch can intervene
_server_module = None
_ingest_module = None
_api_module = None


def _get_modules():
    global _server_module, _ingest_module, _api_module
    if _server_module is None:
        app_dir = Path(__file__).resolve().parent
        original_path = list(sys.path)
        sys.path.insert(0, str(app_dir))
        try:
            for name in ("server", "ingest", "football_api"):
                sys.modules.pop(name, None)
            _server_module = importlib.import_module("server")
            _ingest_module = importlib.import_module("ingest")
            _api_module = importlib.import_module("football_api")
        finally:
            sys.path[:] = original_path
    return _server_module, _ingest_module, _api_module


def _make_client(monkeypatch) -> TestClient:
    """Create a TestClient with an explicit in-memory fake vector store."""
    server, ingest, api = _get_modules()
    fake_store = FakeVectorStoreRegistry()
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "")
    monkeypatch.setattr(server, "FOOTBALL_DATA_API_KEY", "")
    monkeypatch.setattr(ingest, "get_collection", fake_store.get)
    monkeypatch.setattr(server, "get_collection", fake_store.get)
    # Stub embeddings
    monkeypatch.setattr(ingest, "embed_texts", lambda texts: [[0.0] * 1536 for _ in texts])
    return TestClient(server.app, raise_server_exceptions=False)


def _sample_match_result(**overrides) -> dict[str, Any]:
    base = {
        "id": "match-001",
        "text": "Arsenal 3-1 Chelsea",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_score": 3,
        "away_score": 1,
        "competition": "Premier League",
        "competition_id": "PL",
        "matchday": 28,
        "date": "March 5, 2026",
        "venue": "Emirates Stadium",
        "status": "FINISHED",
        "goals": "Saka 12', Havertz 45', Rice 67' - Palmer 55'",
        "live_minute": 0,
        "distance": 0.1,
    }
    base.update(overrides)
    return base


def _sample_standing(**overrides) -> dict[str, Any]:
    base = {
        "id": "standing-pl-1",
        "text": "1. Arsenal W20 D5 L3 · 65 pts",
        "position": 1,
        "team": "Arsenal",
        "won": 20,
        "drawn": 5,
        "lost": 3,
        "gd": 42,
        "points": 65,
        "competition": "Premier League",
        "distance": 0.1,
    }
    base.update(overrides)
    return base


def _sample_scorer(**overrides) -> dict[str, Any]:
    base = {
        "id": "scorer-001",
        "text": "Erling Haaland (Man City): 24 goals (5 pen) · 3 assists",
        "name": "Erling Haaland",
        "team": "Man City",
        "goals": 24,
        "penalties": 5,
        "assists": 3,
        "played_matches": 27,
        "competition": "Premier League",
        "distance": 0.1,
    }
    base.update(overrides)
    return base


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    """Create an httpx.Response with a request set (needed for raise_for_status)."""
    resp = httpx.Response(status_code, json=json_data)
    resp._request = httpx.Request("GET", "https://test.example.com")
    return resp


def _sign(secret: str, timestamp: str, body: str) -> str:
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


# ---------------------------------------------------------------------------
# Football API Client Tests
# ---------------------------------------------------------------------------


class TestFootballDataClient:
    def test_auth_header_set(self):
        _, _, api = _get_modules()
        client = api.FootballDataClient(api_key="test-key")
        assert client._client.headers.get("X-Auth-Token") == "test-key"

    def test_fetch_matches_normalises_response(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "matches": [
                    {
                        "id": 12345,
                        "homeTeam": {"name": "Arsenal"},
                        "awayTeam": {"name": "Chelsea"},
                        "score": {"fullTime": {"home": 3, "away": 1}},
                        "matchday": 28,
                        "utcDate": "2026-03-05T15:00:00Z",
                        "venue": "Emirates Stadium",
                        "status": "FINISHED",
                        "goals": [
                            {"scorer": {"name": "Saka"}, "minute": 12},
                            {"scorer": {"name": "Rice"}, "minute": 67},
                        ],
                    }
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers({"X-Auth-Token": "test"})
        client = api.FootballDataClient(api_key="test", http_client=mock_http)
        result = client.fetch_matches("PL")
        assert len(result) == 1
        assert result[0]["home_team"] == "Arsenal"
        assert result[0]["away_team"] == "Chelsea"
        assert result[0]["home_score"] == 3
        assert result[0]["away_score"] == 1

    def test_fetch_matches_extracts_goals(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "matches": [
                    {
                        "id": 1,
                        "homeTeam": {"name": "A"},
                        "awayTeam": {"name": "B"},
                        "score": {"fullTime": {"home": 2, "away": 0}},
                        "status": "FINISHED",
                        "goals": [
                            {"scorer": {"name": "Player1"}, "minute": 10},
                            {"scorer": {"name": "Player2"}, "minute": 55},
                        ],
                    }
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_matches("PL")
        assert "Player1 10'" in result[0]["goals"]
        assert "Player2 55'" in result[0]["goals"]

    def test_fetch_matches_live_minute(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "matches": [
                    {
                        "id": 2,
                        "homeTeam": {"name": "A"},
                        "awayTeam": {"name": "B"},
                        "score": {"fullTime": {"home": 1, "away": 0}},
                        "status": "IN_PLAY",
                        "minute": 67,
                        "goals": [],
                    }
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_matches("PL")
        assert result[0]["live_minute"] == 67
        assert result[0]["status"] == "IN_PLAY"

    def test_fetch_matches_error_returns_empty(self):
        _, _, api = _get_modules()
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = httpx.ConnectError("fail")
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_matches("PL")
        assert result == []

    def test_fetch_matches_no_score_defaults_to_zero(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "matches": [
                    {
                        "id": 3,
                        "homeTeam": {"name": "A"},
                        "awayTeam": {"name": "B"},
                        "score": {"fullTime": {"home": None, "away": None}},
                        "status": "SCHEDULED",
                        "goals": [],
                    }
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_matches("PL")
        assert result[0]["home_score"] == 0
        assert result[0]["away_score"] == 0

    def test_fetch_standings_normalises(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "standings": [
                    {
                        "type": "TOTAL",
                        "table": [
                            {
                                "position": 1,
                                "team": {"name": "Arsenal"},
                                "playedGames": 28,
                                "won": 20,
                                "draw": 5,
                                "lost": 3,
                                "goalDifference": 42,
                                "points": 65,
                            }
                        ],
                    }
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_standings("PL")
        assert len(result) == 1
        assert result[0]["team"] == "Arsenal"
        assert result[0]["points"] == 65
        assert result[0]["won"] == 20

    def test_fetch_standings_skips_non_total(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "standings": [
                    {"type": "HOME", "table": [{"position": 1, "team": {"name": "X"}, "playedGames": 10, "won": 8, "draw": 1, "lost": 1, "goalDifference": 10, "points": 25}]},
                    {"type": "TOTAL", "table": [{"position": 1, "team": {"name": "Arsenal"}, "playedGames": 28, "won": 20, "draw": 5, "lost": 3, "goalDifference": 42, "points": 65}]},
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_standings("PL")
        assert len(result) == 1
        assert result[0]["team"] == "Arsenal"

    def test_fetch_standings_error_returns_empty(self):
        _, _, api = _get_modules()
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = httpx.ConnectError("fail")
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        assert client.fetch_standings("PL") == []

    def test_fetch_scorers_normalises(self):
        _, _, api = _get_modules()
        mock_response = _mock_response(
            200,{
                "scorers": [
                    {
                        "player": {"id": 1, "name": "Haaland"},
                        "team": {"name": "Man City"},
                        "goals": 24,
                        "penalties": 5,
                        "assists": 3,
                        "playedMatches": 27,
                    }
                ]
            },
        )
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_response
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        result = client.fetch_scorers("PL")
        assert len(result) == 1
        assert result[0]["name"] == "Haaland"
        assert result[0]["goals"] == 24
        assert result[0]["penalties"] == 5
        assert result[0]["assists"] == 3

    def test_fetch_scorers_error_returns_empty(self):
        _, _, api = _get_modules()
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = httpx.ConnectError("fail")
        mock_http.headers = httpx.Headers()
        client = api.FootballDataClient(api_key="k", http_client=mock_http)
        assert client.fetch_scorers("PL") == []

    def test_competitions_dict(self):
        _, _, api = _get_modules()
        assert "PL" in api.COMPETITIONS
        assert "PD" in api.COMPETITIONS
        assert "BSA" in api.COMPETITIONS

    def test_extract_goals_empty(self):
        _, _, api = _get_modules()
        assert api.FootballDataClient._extract_goals([]) == ""


# ---------------------------------------------------------------------------
# Intent Detection Tests
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_scores_intent(self):
        server, _, _ = _get_modules()
        assert server.detect_intent("What's the Arsenal score?") == "scores"

    def test_standings_intent(self):
        server, _, _ = _get_modules()
        assert server.detect_intent("Show me the Premier League table") == "standings"

    def test_scorers_intent(self):
        server, _, _ = _get_modules()
        assert server.detect_intent("Who is the top scorer?") == "scorers"

    def test_general_intent(self):
        server, _, _ = _get_modules()
        assert server.detect_intent("Tell me about football") == "general"

    def test_standings_priority_over_scores(self):
        server, _, _ = _get_modules()
        # "table" triggers standings even if "score" is present
        assert server.detect_intent("league table scores") == "standings"

    def test_scorers_priority_over_scores(self):
        server, _, _ = _get_modules()
        assert server.detect_intent("top scorer in the game") == "scorers"

    def test_case_insensitive(self):
        server, _, _ = _get_modules()
        assert server.detect_intent("PREMIER LEAGUE TABLE") == "standings"


# ---------------------------------------------------------------------------
# Match Formatting Tests
# ---------------------------------------------------------------------------


class TestMatchFormatting:
    def test_format_match_text_finished(self):
        ingest, _, _ = _get_modules()
        # ingest is actually server here due to import order, let me fix
        _, ingest, _ = _get_modules()
        m = {"home_team": "Arsenal", "away_team": "Chelsea", "home_score": 3, "away_score": 1, "competition": "Premier League", "matchday": 28, "date": "March 5, 2026", "goals": "Saka 12'", "venue": "Emirates", "status": "FINISHED"}
        text = ingest.format_match_text(m)
        assert "Arsenal 3-1 Chelsea" in text
        assert "Saka 12'" in text

    def test_format_match_text_live_with_minute(self):
        _, ingest, _ = _get_modules()
        m = {"home_team": "A", "away_team": "B", "home_score": 1, "away_score": 0, "competition": "PL", "matchday": 1, "date": "today", "goals": "", "status": "IN_PLAY", "live_minute": 67}
        text = ingest.format_match_text(m)
        assert "[LIVE 67']" in text

    def test_format_match_text_live_no_minute(self):
        _, ingest, _ = _get_modules()
        m = {"home_team": "A", "away_team": "B", "home_score": 0, "away_score": 0, "competition": "PL", "matchday": 1, "date": "today", "goals": "", "status": "IN_PLAY"}
        text = ingest.format_match_text(m)
        assert "[LIVE]" in text

    def test_match_to_card_finished(self):
        server, _, _ = _get_modules()
        card = server.match_to_card(_sample_match_result())
        assert card["type"] == "match_result"
        assert "Arsenal" in card["title"]
        assert "3-1" in card["title"]
        assert "Full Time" in card["badges"]

    def test_match_to_card_live(self):
        server, _, _ = _get_modules()
        card = server.match_to_card(_sample_match_result(status="IN_PLAY", live_minute=78))
        assert "LIVE 78'" in card["badges"]

    def test_match_to_card_upcoming(self):
        server, _, _ = _get_modules()
        card = server.match_to_card(_sample_match_result(status="SCHEDULED"))
        assert "Upcoming" in card["badges"]


# ---------------------------------------------------------------------------
# Standings Formatting Tests
# ---------------------------------------------------------------------------


class TestStandingsFormatting:
    def test_format_standings_text(self):
        _, ingest, _ = _get_modules()
        standings = [{"position": 1, "team": "Arsenal", "won": 20, "drawn": 5, "lost": 3, "gd": 42, "points": 65}]
        text = ingest.format_standings_text(standings, "Premier League")
        assert "Premier League Standings" in text
        assert "W20 D5 L3" in text
        assert "65 pts" in text

    def test_build_standings_card(self):
        server, _, _ = _get_modules()
        standings = [_sample_standing()]
        card = server.build_standings_card(standings, "Premier League")
        assert card["type"] == "standings_table"
        assert "Premier League" in card["title"]

    def test_build_standings_card_fields(self):
        server, _, _ = _get_modules()
        standings = [_sample_standing()]
        card = server.build_standings_card(standings, "Premier League")
        assert len(card["fields"]) == 1
        assert "W20" in card["fields"][0]["value"]
        assert "D5" in card["fields"][0]["value"]
        assert "L3" in card["fields"][0]["value"]

    def test_build_standings_card_top5_limit(self):
        server, _, _ = _get_modules()
        standings = [_sample_standing(position=i, team=f"Team{i}") for i in range(1, 8)]
        card = server.build_standings_card(standings, "PL")
        assert len(card["fields"]) == 5


# ---------------------------------------------------------------------------
# Scorer Formatting Tests
# ---------------------------------------------------------------------------


class TestScorerFormatting:
    def test_format_scorer_text(self):
        _, ingest, _ = _get_modules()
        s = {"name": "Haaland", "team": "Man City", "goals": 24, "penalties": 5, "assists": 3, "competition": "Premier League"}
        text = ingest.format_scorer_text(s)
        assert "Haaland" in text
        assert "24 goals" in text
        assert "(5 pen)" in text
        assert "3 assists" in text

    def test_format_scorer_no_penalties(self):
        _, ingest, _ = _get_modules()
        s = {"name": "Saka", "team": "Arsenal", "goals": 15, "penalties": 0, "assists": 10, "competition": "PL"}
        text = ingest.format_scorer_text(s)
        assert "pen" not in text

    def test_build_scorers_card(self):
        server, _, _ = _get_modules()
        scorers = [_sample_scorer()]
        card = server.build_scorers_card(scorers, "Premier League")
        assert card["type"] == "top_scorers"
        assert "Premier League" in card["title"]

    def test_build_scorers_card_penalties_in_value(self):
        server, _, _ = _get_modules()
        scorers = [_sample_scorer()]
        card = server.build_scorers_card(scorers, "PL")
        assert "(5 pen)" in card["fields"][0]["value"]


# ---------------------------------------------------------------------------
# Webhook Scores Tests
# ---------------------------------------------------------------------------


class TestWebhookScores:
    def test_scores_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[_sample_match_result()]):
            with patch.object(server, "call_llm", return_value="Arsenal won 3-1"):
                resp = client.post("/", json={"message": {"content": "Arsenal score"}})
        assert resp.status_code == 200

    def test_scores_has_cards(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[_sample_match_result()]):
            with patch.object(server, "call_llm", return_value="Arsenal won"):
                resp = client.post("/", json={"message": {"content": "Arsenal score"}})
        data = resp.json()
        assert len(data["cards"]) > 0
        assert data["cards"][0]["type"] == "match_result"

    def test_scores_has_actions(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[_sample_match_result()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "Arsenal score"}})
        data = resp.json()
        assert len(data["actions"]) > 0

    def test_scores_schema_version(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[_sample_match_result()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "score"}})
        data = resp.json()
        assert data["schema_version"] == "2026-03-01"
        assert data["task"]["status"] == "completed"
        assert data["capability"]["name"] == "football.live"
        assert isinstance(data["artifacts"], list)

    def test_scores_live_badge(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        live_match = _sample_match_result(status="IN_PLAY", live_minute=78)
        with patch.object(server, "search_matches", return_value=[live_match]):
            with patch.object(server, "call_llm", return_value="live"):
                resp = client.post("/", json={"message": {"content": "live score"}})
        cards = resp.json()["cards"]
        assert any("LIVE" in str(c.get("badges", [])) for c in cards)


# ---------------------------------------------------------------------------
# Webhook Standings Tests
# ---------------------------------------------------------------------------


class TestWebhookStandings:
    def test_standings_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_standings", return_value=[_sample_standing()]):
            with patch.object(server, "call_llm", return_value="Arsenal top"):
                resp = client.post("/", json={"message": {"content": "Premier League table"}})
        assert resp.status_code == 200

    def test_standings_card_type(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_standings", return_value=[_sample_standing()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "league table"}})
        cards = resp.json()["cards"]
        assert any(c["type"] == "standings_table" for c in cards)

    def test_standings_has_actions(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_standings", return_value=[_sample_standing()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "standings"}})
        assert len(resp.json()["actions"]) > 0


# ---------------------------------------------------------------------------
# Webhook Scorers Tests
# ---------------------------------------------------------------------------


class TestWebhookScorers:
    def test_scorers_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_scorers", return_value=[_sample_scorer()]):
            with patch.object(server, "call_llm", return_value="Haaland leads"):
                resp = client.post("/", json={"message": {"content": "top scorer"}})
        assert resp.status_code == 200

    def test_scorers_card_type(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_scorers", return_value=[_sample_scorer()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "who scored the most"}})
        cards = resp.json()["cards"]
        assert any(c["type"] == "top_scorers" for c in cards)

    def test_scorers_competition_in_title(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_scorers", return_value=[_sample_scorer()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "top scorer"}})
        cards = resp.json()["cards"]
        scorer_cards = [c for c in cards if c["type"] == "top_scorers"]
        assert any("Premier League" in c["title"] for c in scorer_cards)

    def test_scorers_has_actions(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_scorers", return_value=[_sample_scorer()]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "scorers"}})
        assert len(resp.json()["actions"]) > 0


# ---------------------------------------------------------------------------
# HMAC Signature Tests
# ---------------------------------------------------------------------------


class TestHMACSignature:
    def test_valid_signature_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "WEBHOOK_SECRET", "test-secret")
        body = '{"message":{"content":"score"}}'
        ts = "1700000000"
        sig = _sign("test-secret", ts, body)
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="no data"):
                resp = client.post(
                    "/",
                    data=body,
                    headers={"Content-Type": "application/json", "x-timestamp": ts, "x-signature": sig},
                )
        assert resp.status_code == 200

    def test_invalid_signature_401(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "WEBHOOK_SECRET", "test-secret")
        body = '{"message":{"content":"score"}}'
        resp = client.post(
            "/",
            data=body,
            headers={"Content-Type": "application/json", "x-timestamp": "123", "x-signature": "sha256=wrong"},
        )
        assert resp.status_code == 401

    def test_missing_signature_401(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "WEBHOOK_SECRET", "test-secret")
        resp = client.post("/", json={"message": {"content": "score"}})
        assert resp.status_code == 401

    def test_no_secret_skips_verification(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "WEBHOOK_SECRET", "")
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "score"}})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# SSE Streaming Tests
# ---------------------------------------------------------------------------


class TestSSEStreaming:
    def test_stream_with_accept_header(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'hello'})}\n\n"

        with patch.object(server, "search_matches", return_value=[_sample_match_result()]):
            with patch.object(server, "stream_llm", side_effect=_fake_stream):
                resp = client.post(
                    "/",
                    json={"message": {"content": "score"}},
                    headers={"Accept": "text/event-stream"},
                )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert "event: task.started" in resp.text
        assert "event: task.delta" in resp.text
        assert "event: done" in resp.text

    def test_sse_done_event(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "STREAMING_ENABLED", True)

        async def _fake_stream(_s, _u):
            yield f"data: {json.dumps({'type': 'delta', 'text': 'ok'})}\n\n"

        with patch.object(server, "search_matches", return_value=[_sample_match_result()]):
            with patch.object(server, "stream_llm", side_effect=_fake_stream):
                resp = client.post(
                    "/",
                    json={"message": {"content": "score"}},
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
        assert done["capability"]["name"] == "football.live"
        assert isinstance(done["artifacts"], list)

    def test_json_fallback_when_no_accept(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "STREAMING_ENABLED", True)
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={"message": {"content": "score"}})
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_stream_disabled_returns_json(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "STREAMING_ENABLED", False)
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post(
                    "/",
                    json={"message": {"content": "score"}},
                    headers={"Accept": "text/event-stream"},
                )
        assert resp.headers.get("content-type", "").startswith("application/json")


# ---------------------------------------------------------------------------
# Ingest Endpoint Tests
# ---------------------------------------------------------------------------


class TestIngestEndpoints:
    def test_ingest_requires_api_key(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "FOOTBALL_DATA_API_KEY", "")
        resp = client.post("/ingest")
        assert resp.status_code == 400

    def test_ingest_live_requires_api_key(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "FOOTBALL_DATA_API_KEY", "")
        resp = client.post("/ingest/live")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Health Endpoint Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_collections_and_timestamp(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.get("/health")
        data = resp.json()
        assert "collections" in data
        assert "vector_store" in data
        assert "timestamp" in data
        assert "matches" in data["collections"]
        assert "standings" in data["collections"]
        assert "scorers" in data["collections"]
        assert "backend" in data["vector_store"]
        assert "durable" in data["vector_store"]

    def test_vector_store_metadata_pgvector_is_durable(self, monkeypatch):
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "VECTOR_STORE_BACKEND", "pgvector")
        data = server._vector_store_metadata()
        assert data["backend"] == "pgvector"
        assert data["durable"] is True

    def test_pgvector_backend_requires_dsn(self, monkeypatch):
        _, ingest, _ = _get_modules()
        monkeypatch.setattr(ingest, "VECTOR_STORE_BACKEND", "pgvector")
        monkeypatch.setattr(ingest, "PGVECTOR_DSN", "")
        monkeypatch.setattr(ingest, "_pg_conn", None)
        ingest._pg_collections.clear()

        collection = ingest.get_collection(ingest.COLLECTION_MATCHES)
        with pytest.raises(RuntimeError, match="(PGVECTOR_DSN is required|psycopg is required)"):
            collection.count()


# ---------------------------------------------------------------------------
# Admin Endpoint Tests
# ---------------------------------------------------------------------------


class TestAdminEndpoints:
    def test_admin_status_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.get("/admin/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "leagues" in data
        assert set(data["leagues"]) == {"PL", "PD", "BSA"}

    def test_admin_refresh_requires_api_key(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        monkeypatch.setattr(server, "FOOTBALL_DATA_API_KEY", "")
        resp = client.post("/admin/refresh")
        assert resp.status_code == 400


class TestAgentCard:
    def test_agent_card_has_capability(self, monkeypatch):
        client = _make_client(monkeypatch)
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "nexo-football-live"
        assert data["capabilities"]["items"][0]["name"] == "football.live"


# ---------------------------------------------------------------------------
# Seed Data Tests
# ---------------------------------------------------------------------------


class TestSeedData:
    def test_seed_matches_required_fields(self):
        _, ingest, _ = _get_modules()
        required = {"id", "home_team", "away_team", "home_score", "away_score", "competition", "date", "goals", "status"}
        for match in ingest.SEED_MATCHES:
            missing = required - set(match.keys())
            assert not missing, f"Match {match.get('id')} missing: {missing}"

    def test_seed_matches_count(self):
        _, ingest, _ = _get_modules()
        assert len(ingest.SEED_MATCHES) == 15

    def test_seed_matches_three_leagues(self):
        _, ingest, _ = _get_modules()
        comps = {m["competition_id"] for m in ingest.SEED_MATCHES}
        assert comps == {"PL", "PD", "BSA"}

    def test_seed_standings_count(self):
        _, ingest, _ = _get_modules()
        assert len(ingest.SEED_STANDINGS) == 30

    def test_seed_standings_three_leagues(self):
        _, ingest, _ = _get_modules()
        comps = {s["competition_id"] for s in ingest.SEED_STANDINGS}
        assert comps == {"PL", "PD", "BSA"}

    def test_seed_standings_ordered_by_position(self):
        _, ingest, _ = _get_modules()
        for comp_id in ("PL", "PD", "BSA"):
            positions = [s["position"] for s in ingest.SEED_STANDINGS if s["competition_id"] == comp_id]
            assert positions == sorted(positions), f"{comp_id} standings not ordered"

    def test_seed_scorers_count(self):
        _, ingest, _ = _get_modules()
        assert len(ingest.SEED_SCORERS) == 15

    def test_seed_scorers_three_leagues(self):
        _, ingest, _ = _get_modules()
        comps = {s["competition_id"] for s in ingest.SEED_SCORERS}
        assert comps == {"PL", "PD", "BSA"}

    def test_seed_scorers_required_fields(self):
        _, ingest, _ = _get_modules()
        required = {"id", "name", "team", "goals", "competition", "competition_id"}
        for scorer in ingest.SEED_SCORERS:
            missing = required - set(scorer.keys())
            assert not missing, f"Scorer {scorer.get('id')} missing: {missing}"


# ---------------------------------------------------------------------------
# Multi-League Tests
# ---------------------------------------------------------------------------


class TestMultiLeague:
    def test_all_three_codes_in_seed_matches(self):
        _, ingest, _ = _get_modules()
        codes = {m["competition_id"] for m in ingest.SEED_MATCHES}
        assert codes == {"PL", "PD", "BSA"}

    def test_all_three_codes_in_seed_standings(self):
        _, ingest, _ = _get_modules()
        codes = {s["competition_id"] for s in ingest.SEED_STANDINGS}
        assert codes == {"PL", "PD", "BSA"}

    def test_all_three_codes_in_seed_scorers(self):
        _, ingest, _ = _get_modules()
        codes = {s["competition_id"] for s in ingest.SEED_SCORERS}
        assert codes == {"PL", "PD", "BSA"}

    def test_five_matches_per_league(self):
        _, ingest, _ = _get_modules()
        for code in ("PL", "PD", "BSA"):
            count = sum(1 for m in ingest.SEED_MATCHES if m["competition_id"] == code)
            assert count == 5, f"{code} has {count} matches, expected 5"


# ---------------------------------------------------------------------------
# Personalisation Tests
# ---------------------------------------------------------------------------


class TestPersonalisation:
    def test_display_name_used(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="Arsenal won"):
                resp = client.post("/", json={
                    "message": {"content": "score"},
                    "profile": {"display_name": "Mark"},
                })
        assert "Mark" in resp.json()["content_parts"][0]["text"]

    def test_fallback_to_name(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="ok"):
                resp = client.post("/", json={
                    "message": {"content": "score"},
                    "profile": {"name": "Alice"},
                })
        assert "Alice" in resp.json()["content_parts"][0]["text"]

    def test_no_name_no_prefix(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="result here"):
                resp = client.post("/", json={"message": {"content": "score"}})
        text = resp.json()["content_parts"][0]["text"]
        assert not text.startswith("Hey ")


# ---------------------------------------------------------------------------
# No Results Fallback Tests
# ---------------------------------------------------------------------------


class TestNoResultsFallback:
    def test_empty_results_still_200(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="No data available"):
                resp = client.post("/", json={"message": {"content": "score"}})
        assert resp.status_code == 200
        assert resp.json()["cards"] == []

    def test_personalised_fallback(self, monkeypatch):
        client = _make_client(monkeypatch)
        server, _, _ = _get_modules()
        with patch.object(server, "search_matches", return_value=[]):
            with patch.object(server, "call_llm", return_value="Sorry, no data"):
                resp = client.post("/", json={
                    "message": {"content": "score"},
                    "profile": {"display_name": "Mark"},
                })
        assert "Mark" in resp.json()["content_parts"][0]["text"]
