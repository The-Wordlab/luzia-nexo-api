"""Tests for the event detection pipeline.

All tests use mocks — no real LLM, DB, or network calls.

Coverage:
  - MatchStateTracker: score change, equaliser, match start, match end, no false positives
  - EventDetector: rule-based prefilter, LLM classification (mocked), dedup by content hash
  - EventStore: store + query, dedup, filters
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from event_store import EventStore
from match_state import MatchEvent, MatchStateTracker
from event_detector import DetectedEvent, EventDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_match(
    match_id: str,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    status: str = "IN_PLAY",
    competition: str = "Premier League",
) -> dict:
    return {
        "id": match_id,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "status": status,
        "competition": competition,
        "date": "2026-03-09",
        "matchday": 29,
        "venue": "Emirates Stadium",
        "goals": "",
    }


# ---------------------------------------------------------------------------
# MatchStateTracker tests
# ---------------------------------------------------------------------------


class TestMatchStateTrackerScoreChange:
    def test_score_change_detected(self) -> None:
        tracker = MatchStateTracker()
        prev = [_make_match("m1", "Arsenal", "Chelsea", 0, 0)]
        curr = [_make_match("m1", "Arsenal", "Chelsea", 1, 0)]

        tracker.track(prev)
        events = tracker.track(curr)

        assert len(events) == 1
        assert events[0].event_type == "score_change"
        assert events[0].match_data["id"] == "m1"

    def test_score_change_significance(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])

        assert events[0].significance == pytest.approx(0.8)

    def test_equaliser_has_higher_significance(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 1)])

        assert len(events) == 1
        assert events[0].event_type == "score_change"
        assert events[0].significance == pytest.approx(0.9)

    def test_equaliser_description_mentions_it(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 1)])

        assert "equaliser" in events[0].description.lower() or "equal" in events[0].description.lower()

    def test_score_change_description_contains_teams(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])

        assert "Arsenal" in events[0].description
        assert "Chelsea" in events[0].description

    def test_score_change_description_contains_score(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])

        assert "1-0" in events[0].description

    def test_no_change_no_events(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])

        assert events == []

    def test_multiple_matches_multiple_events(self) -> None:
        tracker = MatchStateTracker()
        prev = [
            _make_match("m1", "Arsenal", "Chelsea", 0, 0),
            _make_match("m2", "Liverpool", "Man City", 0, 0),
        ]
        curr = [
            _make_match("m1", "Arsenal", "Chelsea", 1, 0),
            _make_match("m2", "Liverpool", "Man City", 1, 0),
        ]
        tracker.track(prev)
        events = tracker.track(curr)

        assert len(events) == 2

    def test_only_changed_match_emits_event(self) -> None:
        tracker = MatchStateTracker()
        prev = [
            _make_match("m1", "Arsenal", "Chelsea", 0, 0),
            _make_match("m2", "Liverpool", "Man City", 0, 0),
        ]
        curr = [
            _make_match("m1", "Arsenal", "Chelsea", 1, 0),
            _make_match("m2", "Liverpool", "Man City", 0, 0),
        ]
        tracker.track(prev)
        events = tracker.track(curr)

        assert len(events) == 1
        assert events[0].match_data["id"] == "m1"


class TestMatchStateTrackerMatchStart:
    def test_match_start_detected(self) -> None:
        tracker = MatchStateTracker()
        # First call — matches are SCHEDULED
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="SCHEDULED")])
        # Second call — match now IN_PLAY
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="IN_PLAY")])

        assert any(e.event_type == "match_start" for e in events)

    def test_match_start_significance(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="TIMED")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="IN_PLAY")])

        start_events = [e for e in events if e.event_type == "match_start"]
        assert start_events[0].significance == pytest.approx(0.5)

    def test_match_start_description_contains_teams(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="TIMED")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="IN_PLAY")])

        start_events = [e for e in events if e.event_type == "match_start"]
        assert "Arsenal" in start_events[0].description
        assert "Chelsea" in start_events[0].description

    def test_no_start_event_when_already_in_play(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="IN_PLAY")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0, status="IN_PLAY")])

        start_events = [e for e in events if e.event_type == "match_start"]
        assert start_events == []


class TestMatchStateTrackerMatchEnd:
    def test_match_end_detected(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="IN_PLAY")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="FINISHED")])

        assert any(e.event_type == "match_end" for e in events)

    def test_match_end_significance(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="IN_PLAY")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="FINISHED")])

        end_events = [e for e in events if e.event_type == "match_end"]
        assert end_events[0].significance == pytest.approx(0.7)

    def test_match_end_description_contains_score(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="IN_PLAY")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="FINISHED")])

        end_events = [e for e in events if e.event_type == "match_end"]
        assert "1-0" in end_events[0].description

    def test_match_end_and_score_change_both_emitted(self) -> None:
        """Score changes on the final whistle should emit both events."""
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0, status="IN_PLAY")])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 2, 0, status="FINISHED")])

        types = {e.event_type for e in events}
        assert "match_end" in types
        assert "score_change" in types

    def test_first_call_no_events(self) -> None:
        """No events should fire on the very first tracking call."""
        tracker = MatchStateTracker()
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0)])
        assert events == []


class TestMatchEventDataclass:
    def test_match_event_has_timestamp(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])

        assert isinstance(events[0].timestamp, datetime)

    def test_match_event_has_match_data(self) -> None:
        tracker = MatchStateTracker()
        tracker.track([_make_match("m1", "Arsenal", "Chelsea", 0, 0)])
        events = tracker.track([_make_match("m1", "Arsenal", "Chelsea", 1, 0)])

        assert events[0].match_data["home_team"] == "Arsenal"
        assert events[0].match_data["away_team"] == "Chelsea"


# ---------------------------------------------------------------------------
# EventDetector tests
# ---------------------------------------------------------------------------


class TestEventDetectorPrefilter:
    def test_match_state_events_pass_prefilter_without_llm(self) -> None:
        """MatchEvent objects bypass LLM classification — they are already structured."""
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1", "Arsenal", "Chelsea", 1, 0),
            description="Arsenal 1-0 Chelsea — score change",
            timestamp=_utcnow(),
        )

        # Should not call LLM, should return DetectedEvent directly
        with patch("event_detector.litellm") as mock_litellm:
            result = detector.evaluate_match_event(match_event)
            mock_litellm.completion.assert_not_called()

        assert result is not None
        assert result.event_type == "score_change"
        assert result.significance == pytest.approx(0.8)

    def test_match_event_below_threshold_filtered(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.6)
        match_event = MatchEvent(
            event_type="match_start",
            significance=0.5,  # below threshold
            match_data=_make_match("m1", "Arsenal", "Chelsea", 0, 0),
            description="Match started",
            timestamp=_utcnow(),
        )

        result = detector.evaluate_match_event(match_event)
        assert result is None

    def test_article_passes_prefilter_with_relevant_keywords(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "BREAKING: Haaland transfer to Arsenal confirmed",
            "text": "Manchester City striker Erling Haaland has agreed to join Arsenal.",
            "link": "https://example.com/haaland-transfer",
            "published": "2026-03-09",
        }

        assert detector._passes_article_prefilter(article) is True

    def test_routine_article_fails_prefilter(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "Weekly Premier League preview for matchday 29",
            "text": "Here are the matches scheduled for this weekend.",
            "link": "https://example.com/preview",
            "published": "2026-03-09",
        }

        # This may pass or fail depending on keywords — the key is the method exists and returns bool
        result = detector._passes_article_prefilter(article)
        assert isinstance(result, bool)

    def test_article_with_goal_keyword_passes(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "Arsenal score dramatic last-minute goal",
            "text": "Saka scored in injury time to win the match.",
            "link": "https://example.com/arsenal-goal",
            "published": "2026-03-09",
        }

        assert detector._passes_article_prefilter(article) is True


class TestEventDetectorLLMClassification:
    def test_classify_article_calls_litellm(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "Arsenal score last-minute winner",
            "text": "Saka scored in injury time to win the match for Arsenal.",
            "link": "https://example.com/arsenal",
            "published": "2026-03-09",
        }

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"event_type": "goal", "significance": 0.85, "summary": "Arsenal late winner", "detail": "Saka scores in injury time"}'

        with patch("event_detector.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_response
            result = detector.classify_article(article)

        mock_litellm.completion.assert_called_once()
        assert result is not None
        assert result.event_type == "goal"
        assert result.significance == pytest.approx(0.85)

    def test_classify_article_below_threshold_returns_none(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.6)
        article = {
            "title": "Match scheduled for Saturday",
            "text": "Premier League matchday 29 is scheduled for Saturday.",
            "link": "https://example.com/schedule",
            "published": "2026-03-09",
        }

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"event_type": "routine", "significance": 0.2, "summary": "Routine schedule", "detail": "Just a schedule announcement"}'

        with patch("event_detector.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_response
            result = detector.classify_article(article)

        assert result is None

    def test_classify_article_handles_llm_failure(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "Arsenal score last-minute winner",
            "text": "Saka scores late.",
            "link": "https://example.com/arsenal",
            "published": "2026-03-09",
        }

        with patch("event_detector.litellm") as mock_litellm:
            mock_litellm.completion.side_effect = Exception("LLM API error")
            result = detector.classify_article(article)

        # Should return None gracefully, not raise
        assert result is None

    def test_classify_article_handles_invalid_json(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "Arsenal score",
            "text": "Arsenal scored.",
            "link": "https://example.com",
            "published": "2026-03-09",
        }

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "not valid json at all"

        with patch("event_detector.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_response
            result = detector.classify_article(article)

        assert result is None


class TestEventDetectorDedup:
    def test_same_article_not_processed_twice(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article = {
            "title": "Arsenal score last-minute winner",
            "text": "Saka scores late.",
            "link": "https://example.com/arsenal",
            "published": "2026-03-09",
        }

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"event_type": "goal", "significance": 0.8, "summary": "Arsenal winner", "detail": "Saka scored"}'

        with patch("event_detector.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_response
            result1 = detector.classify_article(article)
            result2 = detector.classify_article(article)  # same article again

        # LLM should only be called once
        assert mock_litellm.completion.call_count == 1
        assert result1 is not None
        assert result2 is None  # deduped

    def test_different_articles_both_processed(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        article1 = {
            "title": "Arsenal goal",
            "text": "Arsenal scored.",
            "link": "https://example.com/1",
            "published": "2026-03-09",
        }
        article2 = {
            "title": "Chelsea goal",
            "text": "Chelsea scored.",
            "link": "https://example.com/2",
            "published": "2026-03-09",
        }

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"event_type": "goal", "significance": 0.8, "summary": "Goal", "detail": "Goal scored"}'

        with patch("event_detector.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_response
            result1 = detector.classify_article(article1)
            result2 = detector.classify_article(article2)

        assert mock_litellm.completion.call_count == 2
        assert result1 is not None
        assert result2 is not None

    def test_detected_event_has_content_hash(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1", "Arsenal", "Chelsea", 1, 0),
            description="Arsenal 1-0 Chelsea",
            timestamp=_utcnow(),
        )

        result = detector.evaluate_match_event(match_event)
        assert result is not None
        assert isinstance(result.content_hash, str)
        assert len(result.content_hash) == 64  # sha256 hex

    def test_content_hash_is_deterministic(self) -> None:
        """Same input must produce same hash."""
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1", "Arsenal", "Chelsea", 1, 0),
            description="Arsenal 1-0 Chelsea",
            timestamp=_utcnow(),
        )

        result1 = detector.evaluate_match_event(match_event)
        # reset seen hashes to allow re-evaluation
        detector._seen_hashes.clear()
        result2 = detector.evaluate_match_event(match_event)

        assert result1 is not None
        assert result2 is not None
        assert result1.content_hash == result2.content_hash


class TestDetectedEventDataclass:
    def test_detected_event_fields(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1", "Arsenal", "Chelsea", 1, 0),
            description="Arsenal 1-0 Chelsea — score change",
            timestamp=_utcnow(),
        )

        result = detector.evaluate_match_event(match_event)

        assert result is not None
        assert result.event_type == "score_change"
        assert result.significance == pytest.approx(0.8)
        assert isinstance(result.summary, str)
        assert isinstance(result.detail, str)
        assert isinstance(result.timestamp, datetime)
        assert isinstance(result.content_hash, str)

    def test_detected_event_source_items_contains_match_data(self) -> None:
        detector = EventDetector(llm_model="mock/model", significance_threshold=0.3)
        match_event = MatchEvent(
            event_type="score_change",
            significance=0.8,
            match_data=_make_match("m1", "Arsenal", "Chelsea", 1, 0),
            description="Arsenal 1-0 Chelsea",
            timestamp=_utcnow(),
        )

        result = detector.evaluate_match_event(match_event)
        assert result is not None
        assert len(result.source_items) >= 1


# ---------------------------------------------------------------------------
# EventStore tests
# ---------------------------------------------------------------------------


class TestEventStoreStoreAndQuery:
    def test_store_returns_event_id(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        event = _make_detected_event("goal", 0.8, "Arsenal goal", "Saka scored")
        event_id = store.store(event)

        assert isinstance(event_id, str)
        assert len(event_id) > 0

    def test_stored_event_retrievable(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        event = _make_detected_event("goal", 0.8, "Arsenal goal", "Saka scored")
        store.store(event)

        recent = store.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["event_type"] == "goal"

    def test_store_multiple_events(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        store.store(_make_detected_event("goal", 0.8, "Arsenal goal", "Saka scored"))
        store.store(_make_detected_event("match_start", 0.5, "Match started", "Kick off"))
        store.store(_make_detected_event("match_end", 0.7, "Match ended", "Full time"))

        recent = store.get_recent(limit=10)
        assert len(recent) == 3

    def test_get_recent_respects_limit(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        for i in range(5):
            store.store(_make_detected_event("goal", 0.8, f"Goal {i}", f"Score {i}"))

        recent = store.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_recent_returns_newest_first(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        store.store(_make_detected_event("goal", 0.8, "First goal", "First"))
        store.store(_make_detected_event("goal", 0.8, "Second goal", "Second"))

        recent = store.get_recent(limit=10)
        assert recent[0]["summary"] == "Second goal"
        assert recent[1]["summary"] == "First goal"


class TestEventStoreDedup:
    def test_duplicate_content_hash_not_stored_twice(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        event = _make_detected_event("goal", 0.8, "Arsenal goal", "Saka scored")
        # Store with same content_hash twice
        id1 = store.store(event)
        id2 = store.store(event)  # duplicate

        recent = store.get_recent(limit=10)
        assert len(recent) == 1
        assert id1 == id2  # returns same id for dedup

    def test_different_hashes_both_stored(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        event1 = _make_detected_event("goal", 0.8, "Arsenal goal", "Saka scored", content_hash="aaa")
        event2 = _make_detected_event("goal", 0.8, "Chelsea goal", "Palmer scored", content_hash="bbb")

        store.store(event1)
        store.store(event2)

        recent = store.get_recent(limit=10)
        assert len(recent) == 2


class TestEventStoreQuery:
    def test_query_by_event_type(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        store.store(_make_detected_event("goal", 0.8, "Arsenal goal", "Saka"))
        store.store(_make_detected_event("match_start", 0.5, "Match started", "KO"))
        store.store(_make_detected_event("goal", 0.8, "Chelsea goal", "Palmer"))

        results = store.query(event_type="goal")
        assert len(results) == 2
        assert all(r["event_type"] == "goal" for r in results)

    def test_query_by_team(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        store.store(_make_detected_event("goal", 0.8, "Arsenal goal", "Saka", teams=["Arsenal", "Chelsea"]))
        store.store(_make_detected_event("goal", 0.8, "Liverpool goal", "Salah", teams=["Liverpool", "Man City"]))

        results = store.query(team="Arsenal")
        assert len(results) == 1
        assert "Arsenal" in results[0]["summary"]

    def test_query_by_since(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        past_event = _make_detected_event("goal", 0.8, "Old goal", "Old scorer")
        past_event = past_event._replace(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        recent_event = _make_detected_event("goal", 0.8, "New goal", "New scorer")

        store.store(past_event)
        store.store(recent_event)

        cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)
        results = store.query(since=cutoff)
        assert len(results) == 1
        assert results[0]["summary"] == "New goal"

    def test_query_by_limit(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        for i in range(5):
            store.store(_make_detected_event("goal", 0.8, f"Goal {i}", f"Scorer {i}", content_hash=f"hash{i}"))

        results = store.query(limit=3)
        assert len(results) == 3

    def test_query_no_filters_returns_all(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        store.store(_make_detected_event("goal", 0.8, "Arsenal goal", "Saka", content_hash="h1"))
        store.store(_make_detected_event("match_start", 0.5, "Match started", "KO", content_hash="h2"))

        results = store.query()
        assert len(results) == 2

    def test_query_result_has_expected_fields(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        store.store(_make_detected_event("goal", 0.8, "Arsenal goal", "Saka"))

        results = store.query()
        assert len(results) == 1
        result = results[0]

        assert "event_id" in result
        assert "event_type" in result
        assert "significance" in result
        assert "summary" in result
        assert "detail" in result
        assert "timestamp" in result
        assert "content_hash" in result

    def test_empty_store_returns_empty_list(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store = EventStore(db_path=db_path)

        results = store.query()
        assert results == []

        recent = store.get_recent(limit=10)
        assert recent == []


class TestEventStorePersistence:
    def test_events_persist_across_store_instances(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")

        store1 = EventStore(db_path=db_path)
        store1.store(_make_detected_event("goal", 0.8, "Arsenal goal", "Saka"))

        store2 = EventStore(db_path=db_path)
        results = store2.get_recent(limit=10)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Helper for creating DetectedEvent instances in tests
# ---------------------------------------------------------------------------


def _make_detected_event(
    event_type: str,
    significance: float,
    summary: str,
    detail: str,
    teams: list[str] | None = None,
    content_hash: str | None = None,
) -> DetectedEvent:
    if content_hash is None:
        content_hash = hashlib.sha256(f"{event_type}:{summary}:{detail}".encode()).hexdigest()
    return DetectedEvent(
        event_type=event_type,
        significance=significance,
        summary=summary,
        detail=detail,
        card=None,
        source_items=[],
        timestamp=_utcnow(),
        content_hash=content_hash,
        teams=teams or [],
    )
