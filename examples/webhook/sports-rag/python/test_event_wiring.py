"""Tests for event detection wiring into server.py.

Coverage:
  - GET /admin/events: returns stored events, query params (type, team, limit)
  - POST /admin/detect: triggers detection cycle, returns detected events
  - Background loop: MatchStateTracker + EventStore called during refresh
  - run_detection_cycle: unit-testable extraction of detection logic
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import ingest as _ingest_module
import server as _server_module
from event_detector import DetectedEvent
from server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client(monkeypatch) -> TestClient:
    """Return a test client with startup hooks stubbed out."""

    def _noop():
        pass

    async def _noop_async(_feeds=None):
        return 0

    monkeypatch.setattr(_ingest_module, "seed_matches", _noop)
    monkeypatch.setattr(_ingest_module, "seed_standings", _noop)
    monkeypatch.setattr(_server_module, "seed_matches", _noop)
    monkeypatch.setattr(_server_module, "seed_standings", _noop)
    monkeypatch.setattr(_ingest_module, "crawl_feeds", _noop_async)

    return TestClient(app)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_detected_event(
    event_type: str = "goal",
    significance: float = 0.8,
    summary: str = "Arsenal goal",
    detail: str = "Saka scored",
    teams: list[str] | None = None,
    content_hash: str | None = None,
) -> DetectedEvent:
    if content_hash is None:
        content_hash = hashlib.sha256(f"{event_type}:{summary}".encode()).hexdigest()
    return DetectedEvent(
        event_type=event_type,
        significance=significance,
        summary=summary,
        detail=detail,
        card=None,
        source_items=[],
        timestamp=_utcnow(),
        content_hash=content_hash,
        teams=teams or ["Arsenal", "Chelsea"],
    )


def _make_match(match_id: str, status: str = "IN_PLAY") -> dict[str, Any]:
    return {
        "id": match_id,
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_score": 1,
        "away_score": 0,
        "status": status,
        "competition": "Premier League",
        "date": "2026-03-09",
        "matchday": 29,
        "venue": "Emirates Stadium",
        "goals": "",
    }


# ---------------------------------------------------------------------------
# GET /admin/events
# ---------------------------------------------------------------------------


class TestAdminEventsGet:
    def test_admin_events_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        resp = client.get("/admin/events")
        assert resp.status_code == 200

    def test_admin_events_response_envelope(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        data = client.get("/admin/events").json()
        assert data["status"] == "ok"
        assert "events" in data
        assert "total" in data
        assert "timestamp" in data

    def test_admin_events_returns_stored_events(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        stored = [
            {
                "event_id": "abc-123",
                "event_type": "goal",
                "significance": 0.8,
                "summary": "Arsenal goal",
                "detail": "Saka scored",
                "teams": ["Arsenal", "Chelsea"],
                "card": None,
                "timestamp": _utcnow().isoformat(),
                "content_hash": "aaa",
            }
        ]
        mock_store = MagicMock()
        mock_store.query.return_value = stored
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        data = client.get("/admin/events").json()
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "goal"
        assert data["total"] == 1

    def test_admin_events_type_filter_passed_to_store(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        client.get("/admin/events?type=goal")
        mock_store.query.assert_called_once()
        call_kwargs = mock_store.query.call_args[1]
        assert call_kwargs.get("event_type") == "goal"

    def test_admin_events_team_filter_passed_to_store(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        client.get("/admin/events?team=Arsenal")
        mock_store.query.assert_called_once()
        call_kwargs = mock_store.query.call_args[1]
        assert call_kwargs.get("team") == "Arsenal"

    def test_admin_events_limit_filter_passed_to_store(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        client.get("/admin/events?limit=5")
        mock_store.query.assert_called_once()
        call_kwargs = mock_store.query.call_args[1]
        assert call_kwargs.get("limit") == 5

    def test_admin_events_default_limit_is_20(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        client.get("/admin/events")
        call_kwargs = mock_store.query.call_args[1]
        assert call_kwargs.get("limit") == 20

    def test_admin_events_combined_filters(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        client.get("/admin/events?type=goal&team=Arsenal&limit=10")
        call_kwargs = mock_store.query.call_args[1]
        assert call_kwargs.get("event_type") == "goal"
        assert call_kwargs.get("team") == "Arsenal"
        assert call_kwargs.get("limit") == 10


# ---------------------------------------------------------------------------
# POST /admin/detect
# ---------------------------------------------------------------------------


class TestAdminDetectPost:
    def test_admin_detect_returns_200(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "run_detection_cycle", AsyncMock(return_value=[]))

        resp = client.post("/admin/detect")
        assert resp.status_code == 200

    def test_admin_detect_response_envelope(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "run_detection_cycle", AsyncMock(return_value=[]))

        data = client.post("/admin/detect").json()
        assert data["status"] == "ok"
        assert "events_detected" in data
        assert "events" in data
        assert "timestamp" in data

    def test_admin_detect_returns_detected_events(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        event = _make_detected_event("goal", 0.8, "Arsenal goal", "Saka")
        monkeypatch.setattr(_server_module, "run_detection_cycle", AsyncMock(return_value=[event]))

        data = client.post("/admin/detect").json()
        assert data["events_detected"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "goal"

    def test_admin_detect_calls_run_detection_cycle(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        mock_cycle = AsyncMock(return_value=[])
        monkeypatch.setattr(_server_module, "run_detection_cycle", mock_cycle)

        client.post("/admin/detect")
        mock_cycle.assert_called_once()

    def test_admin_detect_no_events_returns_empty_list(self, monkeypatch) -> None:
        client = _make_client(monkeypatch)
        monkeypatch.setattr(_server_module, "run_detection_cycle", AsyncMock(return_value=[]))

        data = client.post("/admin/detect").json()
        assert data["events_detected"] == 0
        assert data["events"] == []


# ---------------------------------------------------------------------------
# run_detection_cycle (unit tests)
# ---------------------------------------------------------------------------


class TestRunDetectionCycle:
    @pytest.mark.asyncio
    async def test_detection_cycle_fetches_live_matches(self, monkeypatch) -> None:
        mock_fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(_server_module, "fetch_live_matches", mock_fetch)

        mock_tracker = MagicMock()
        mock_tracker.track.return_value = []
        monkeypatch.setattr(_server_module, "_match_state_tracker", mock_tracker)

        mock_store = MagicMock()
        mock_store.query.return_value = []
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        mock_detector = MagicMock()
        monkeypatch.setattr(_server_module, "_event_detector", mock_detector)

        await _server_module.run_detection_cycle()
        mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_detection_cycle_calls_tracker(self, monkeypatch) -> None:
        matches = [_make_match("m1")]
        monkeypatch.setattr(_server_module, "fetch_live_matches", AsyncMock(return_value=matches))

        mock_tracker = MagicMock()
        mock_tracker.track.return_value = []
        monkeypatch.setattr(_server_module, "_match_state_tracker", mock_tracker)

        mock_store = MagicMock()
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        mock_detector = MagicMock()
        mock_detector.evaluate_match_event.return_value = None
        monkeypatch.setattr(_server_module, "_event_detector", mock_detector)

        await _server_module.run_detection_cycle()
        mock_tracker.track.assert_called_once_with(matches)

    @pytest.mark.asyncio
    async def test_detection_cycle_stores_detected_events(self, monkeypatch) -> None:
        from match_state import MatchEvent

        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1"),
            description="Arsenal 1-0 Chelsea",
            timestamp=_utcnow(),
        )
        monkeypatch.setattr(_server_module, "fetch_live_matches", AsyncMock(return_value=[_make_match("m1")]))

        mock_tracker = MagicMock()
        mock_tracker.track.return_value = [match_event]
        monkeypatch.setattr(_server_module, "_match_state_tracker", mock_tracker)

        detected = _make_detected_event("score_change", 0.8, "Arsenal 1-0 Chelsea", "Score change")
        mock_detector = MagicMock()
        mock_detector.evaluate_match_event.return_value = detected
        monkeypatch.setattr(_server_module, "_event_detector", mock_detector)

        mock_store = MagicMock()
        mock_store.store.return_value = "evt-123"
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        result = await _server_module.run_detection_cycle()
        mock_store.store.assert_called_once_with(detected)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_detection_cycle_skips_none_events(self, monkeypatch) -> None:
        from match_state import MatchEvent

        match_event = MatchEvent(
            event_type="match_start",
            significance=0.5,
            match_data=_make_match("m1"),
            description="Match started",
            timestamp=_utcnow(),
        )
        monkeypatch.setattr(_server_module, "fetch_live_matches", AsyncMock(return_value=[_make_match("m1")]))

        mock_tracker = MagicMock()
        mock_tracker.track.return_value = [match_event]
        monkeypatch.setattr(_server_module, "_match_state_tracker", mock_tracker)

        mock_detector = MagicMock()
        mock_detector.evaluate_match_event.return_value = None  # below threshold
        monkeypatch.setattr(_server_module, "_event_detector", mock_detector)

        mock_store = MagicMock()
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        result = await _server_module.run_detection_cycle()
        mock_store.store.assert_not_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_detection_cycle_returns_detected_events(self, monkeypatch) -> None:
        from match_state import MatchEvent

        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1"),
            description="Arsenal 1-0 Chelsea",
            timestamp=_utcnow(),
        )
        monkeypatch.setattr(_server_module, "fetch_live_matches", AsyncMock(return_value=[_make_match("m1")]))

        mock_tracker = MagicMock()
        mock_tracker.track.return_value = [match_event]
        monkeypatch.setattr(_server_module, "_match_state_tracker", mock_tracker)

        detected = _make_detected_event("score_change", 0.8, "Arsenal 1-0 Chelsea", "Score change")
        mock_detector = MagicMock()
        mock_detector.evaluate_match_event.return_value = detected
        monkeypatch.setattr(_server_module, "_event_detector", mock_detector)

        mock_store = MagicMock()
        mock_store.store.return_value = "evt-123"
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        result = await _server_module.run_detection_cycle()
        assert result == [detected]

    @pytest.mark.asyncio
    async def test_detection_cycle_handles_fetch_failure(self, monkeypatch) -> None:
        monkeypatch.setattr(
            _server_module, "fetch_live_matches", AsyncMock(side_effect=Exception("API down"))
        )

        mock_tracker = MagicMock()
        monkeypatch.setattr(_server_module, "_match_state_tracker", mock_tracker)

        mock_store = MagicMock()
        monkeypatch.setattr(_server_module, "_event_store", mock_store)

        mock_detector = MagicMock()
        monkeypatch.setattr(_server_module, "_event_detector", mock_detector)

        # Should not raise — graceful degradation
        result = await _server_module.run_detection_cycle()
        assert result == []


# ---------------------------------------------------------------------------
# Background loop integration
# ---------------------------------------------------------------------------


class TestBackgroundLoopIntegration:
    def test_module_level_instances_exist(self) -> None:
        """Module-level tracker, detector, and store must be created at import time."""
        assert hasattr(_server_module, "_match_state_tracker")
        assert hasattr(_server_module, "_event_detector")
        assert hasattr(_server_module, "_event_store")

    def test_match_state_tracker_is_correct_type(self) -> None:
        from match_state import MatchStateTracker
        assert isinstance(_server_module._match_state_tracker, MatchStateTracker)

    def test_event_detector_is_correct_type(self) -> None:
        from event_detector import EventDetector
        assert isinstance(_server_module._event_detector, EventDetector)

    def test_event_store_is_correct_type(self) -> None:
        from event_store import EventStore
        assert isinstance(_server_module._event_store, EventStore)

    def test_live_poll_interval_seconds_config_exists(self) -> None:
        """LIVE_POLL_INTERVAL_SECONDS must be a module-level int config."""
        assert hasattr(_server_module, "LIVE_POLL_INTERVAL_SECONDS")
        assert isinstance(_server_module.LIVE_POLL_INTERVAL_SECONDS, int)
        assert _server_module.LIVE_POLL_INTERVAL_SECONDS > 0

    def test_live_monitor_task_attribute_exists(self) -> None:
        """Server must expose a _live_monitor_task attribute for the secondary loop."""
        assert hasattr(_server_module, "_live_monitor_task")
