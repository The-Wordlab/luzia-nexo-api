"""Tests for shared base classes: BaseEventDetector, EventStore, BaseStateTracker.

All tests use mocks — no real LLM, DB, or network calls.

Coverage:
  - BaseEventDetector: prefilter, LLM classify, dedup, threshold filtering
  - EventStore: store + query, dedup, filters, persistence
  - BaseStateTracker: first-call no events, added/removed/changed, custom key_fn
"""

from __future__ import annotations

import hashlib
import sys
import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Allow importing from the shared directory itself
sys.path.insert(0, os.path.dirname(__file__))

from base_event_detector import BaseEventDetector, Event, Classification
from base_event_store import EventStore, StoredEvent
from base_state_tracker import BaseStateTracker, StateChangeEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_stored_event(
    event_type: str,
    significance: float,
    summary: str,
    detail: str,
    teams: list[str] | None = None,
    content_hash: str | None = None,
) -> StoredEvent:
    if content_hash is None:
        content_hash = hashlib.sha256(f"{event_type}:{summary}:{detail}".encode()).hexdigest()
    return StoredEvent(
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


# ---------------------------------------------------------------------------
# Concrete mock subclass of BaseEventDetector for testing
# ---------------------------------------------------------------------------


class MockEventDetector(BaseEventDetector):
    """Minimal concrete subclass used in tests. Both abstract methods can be controlled."""

    def __init__(
        self,
        llm_model: str = "mock/model",
        significance_threshold: float = 0.5,
        prefilter_returns: bool = True,
    ) -> None:
        super().__init__(llm_model=llm_model, significance_threshold=significance_threshold)
        self._prefilter_returns = prefilter_returns

    def _passes_prefilter(self, item: dict[str, Any]) -> bool:
        return self._prefilter_returns

    def _classify(self, item: dict[str, Any]) -> Classification | None:
        # Subclasses would call LLM here; in tests we mock litellm directly
        return None


# ---------------------------------------------------------------------------
# BaseEventDetector tests
# ---------------------------------------------------------------------------


class TestBaseEventDetectorPrefilter:
    def test_item_blocked_by_prefilter_returns_none(self) -> None:
        detector = MockEventDetector(prefilter_returns=False)
        item = {"title": "Some item", "link": "https://example.com/1"}
        result = detector.detect([item])
        assert result == []

    def test_item_passes_prefilter_proceeds_to_classify(self) -> None:
        detector = MockEventDetector(prefilter_returns=True)
        item = {"title": "Breaking news", "link": "https://example.com/1"}

        # _classify returns None by default in MockEventDetector
        result = detector.detect([item])
        assert result == []

    def test_detect_returns_event_when_classify_succeeds(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.3)

        item = {"title": "Breaking news", "link": "https://example.com/1"}

        mock_classification = Classification(
            event_type="breaking_news",
            significance=0.85,
            summary="Something happened",
            detail="More detail here",
        )

        with patch.object(detector, "_classify", return_value=mock_classification):
            result = detector.detect([item])

        assert len(result) == 1
        assert result[0].event_type == "breaking_news"
        assert result[0].significance == pytest.approx(0.85)

    def test_detect_filters_below_threshold(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.7)

        item = {"title": "Minor update", "link": "https://example.com/2"}

        mock_classification = Classification(
            event_type="routine",
            significance=0.3,
            summary="Routine update",
            detail="Nothing interesting",
        )

        with patch.object(detector, "_classify", return_value=mock_classification):
            result = detector.detect([item])

        assert result == []

    def test_detect_multiple_items(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.3)

        items = [
            {"title": "Item 1", "link": "https://example.com/1"},
            {"title": "Item 2", "link": "https://example.com/2"},
        ]

        mock_classification = Classification(
            event_type="news",
            significance=0.8,
            summary="Summary",
            detail="Detail",
        )

        with patch.object(detector, "_classify", return_value=mock_classification):
            result = detector.detect(items)

        assert len(result) == 2


class TestBaseEventDetectorDedup:
    def test_same_item_not_processed_twice(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.3)
        item = {"title": "Breaking", "link": "https://example.com/1"}

        mock_classification = Classification(
            event_type="news",
            significance=0.8,
            summary="Breaking news",
            detail="Something happened",
        )

        classify_mock = MagicMock(return_value=mock_classification)
        with patch.object(detector, "_classify", classify_mock):
            result1 = detector.detect([item])
            result2 = detector.detect([item])  # same item again

        # _classify should only be called once
        assert classify_mock.call_count == 1
        assert len(result1) == 1
        assert result2 == []  # deduped

    def test_different_items_both_processed(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.3)
        item1 = {"title": "Item 1", "link": "https://example.com/1"}
        item2 = {"title": "Item 2", "link": "https://example.com/2"}

        mock_classification = Classification(
            event_type="news",
            significance=0.8,
            summary="News",
            detail="Detail",
        )

        classify_mock = MagicMock(return_value=mock_classification)
        with patch.object(detector, "_classify", classify_mock):
            detector.detect([item1])
            detector.detect([item2])

        assert classify_mock.call_count == 2

    def test_content_hash_is_deterministic(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.3)
        item = {"title": "News", "link": "https://example.com/1"}

        mock_classification = Classification(
            event_type="news",
            significance=0.8,
            summary="Summary",
            detail="Detail",
        )

        with patch.object(detector, "_classify", return_value=mock_classification):
            result = detector.detect([item])

        assert len(result) == 1
        # reset seen hashes and run again — should get same hash
        detector._seen_hashes.clear()
        with patch.object(detector, "_classify", return_value=mock_classification):
            result2 = detector.detect([item])

        assert result[0].content_hash == result2[0].content_hash


class TestBaseEventDetectorEventShape:
    def test_event_has_required_fields(self) -> None:
        detector = MockEventDetector(prefilter_returns=True, significance_threshold=0.3)
        item = {"title": "News", "link": "https://example.com/1"}

        mock_classification = Classification(
            event_type="news",
            significance=0.8,
            summary="Breaking news",
            detail="Full detail",
        )

        with patch.object(detector, "_classify", return_value=mock_classification):
            result = detector.detect([item])

        assert len(result) == 1
        event = result[0]
        assert isinstance(event.event_type, str)
        assert isinstance(event.significance, float)
        assert isinstance(event.summary, str)
        assert isinstance(event.detail, str)
        assert isinstance(event.timestamp, datetime)
        assert isinstance(event.content_hash, str)
        assert len(event.content_hash) == 64  # sha256 hex


class TestClassificationDataclass:
    def test_classification_fields(self) -> None:
        c = Classification(
            event_type="goal",
            significance=0.9,
            summary="Arsenal score",
            detail="Saka fires home",
        )
        assert c.event_type == "goal"
        assert c.significance == pytest.approx(0.9)
        assert c.summary == "Arsenal score"
        assert c.detail == "Saka fires home"

    def test_classification_optional_card(self) -> None:
        c = Classification(
            event_type="goal",
            significance=0.9,
            summary="Goal",
            detail="Detail",
            card={"type": "match_result"},
        )
        assert c.card == {"type": "match_result"}

    def test_classification_default_card_is_none(self) -> None:
        c = Classification(
            event_type="goal",
            significance=0.9,
            summary="Goal",
            detail="Detail",
        )
        assert c.card is None


# ---------------------------------------------------------------------------
# EventStore (generic) tests
# ---------------------------------------------------------------------------


class TestEventStoreStoreAndQuery:
    def test_store_returns_event_id(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        event = _make_stored_event("news", 0.8, "Breaking news", "Detail")
        event_id = store.store(event)
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    def test_stored_event_retrievable(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("news", 0.8, "Breaking news", "Detail"))
        recent = store.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["event_type"] == "news"

    def test_store_multiple_events(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("news", 0.8, "Event 1", "Detail 1", content_hash="h1"))
        store.store(_make_stored_event("alert", 0.6, "Event 2", "Detail 2", content_hash="h2"))
        store.store(_make_stored_event("update", 0.4, "Event 3", "Detail 3", content_hash="h3"))
        recent = store.get_recent(limit=10)
        assert len(recent) == 3

    def test_get_recent_respects_limit(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        for i in range(5):
            store.store(_make_stored_event("news", 0.8, f"Event {i}", f"Detail {i}", content_hash=f"hash{i}"))
        recent = store.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_recent_returns_newest_first(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("news", 0.8, "First event", "First", content_hash="h1"))
        store.store(_make_stored_event("news", 0.8, "Second event", "Second", content_hash="h2"))
        recent = store.get_recent(limit=10)
        assert recent[0]["summary"] == "Second event"
        assert recent[1]["summary"] == "First event"

    def test_query_result_has_expected_fields(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("news", 0.8, "Event", "Detail"))
        results = store.query()
        assert len(results) == 1
        result = results[0]
        for field in ("event_id", "event_type", "significance", "summary", "detail", "timestamp", "content_hash"):
            assert field in result

    def test_empty_store_returns_empty_list(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        assert store.query() == []
        assert store.get_recent(limit=10) == []


class TestEventStoreDedup:
    def test_duplicate_content_hash_not_stored_twice(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        event = _make_stored_event("news", 0.8, "Breaking news", "Detail")
        id1 = store.store(event)
        id2 = store.store(event)  # duplicate
        assert len(store.get_recent(limit=10)) == 1
        assert id1 == id2

    def test_different_hashes_both_stored(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("news", 0.8, "Event 1", "Detail 1", content_hash="aaa"))
        store.store(_make_stored_event("news", 0.8, "Event 2", "Detail 2", content_hash="bbb"))
        assert len(store.get_recent(limit=10)) == 2


class TestEventStoreQueryFilters:
    def test_query_by_event_type(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("goal", 0.8, "Goal 1", "Detail", content_hash="h1"))
        store.store(_make_stored_event("update", 0.5, "Update 1", "Detail", content_hash="h2"))
        store.store(_make_stored_event("goal", 0.8, "Goal 2", "Detail", content_hash="h3"))
        results = store.query(event_type="goal")
        assert len(results) == 2
        assert all(r["event_type"] == "goal" for r in results)

    def test_query_by_since(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        past_event = _make_stored_event("news", 0.8, "Old event", "Old")
        past_event = past_event._replace(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        recent_event = _make_stored_event("news", 0.8, "New event", "New", content_hash="newhash")

        store.store(past_event)
        store.store(recent_event)

        cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)
        results = store.query(since=cutoff)
        assert len(results) == 1
        assert results[0]["summary"] == "New event"

    def test_query_by_limit(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        for i in range(5):
            store.store(_make_stored_event("news", 0.8, f"Event {i}", f"Detail {i}", content_hash=f"hash{i}"))
        results = store.query(limit=3)
        assert len(results) == 3

    def test_query_no_filters_returns_all(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "events.db"))
        store.store(_make_stored_event("news", 0.8, "Event 1", "Detail", content_hash="h1"))
        store.store(_make_stored_event("alert", 0.6, "Event 2", "Detail", content_hash="h2"))
        results = store.query()
        assert len(results) == 2


class TestEventStoreCustomTableName:
    def test_custom_table_name(self, tmp_path) -> None:
        store = EventStore(db_path=str(tmp_path / "custom.db"), table_name="my_events")
        store.store(_make_stored_event("news", 0.8, "Event", "Detail"))
        results = store.get_recent(limit=10)
        assert len(results) == 1

    def test_two_stores_different_table_names_isolated(self, tmp_path) -> None:
        db_path = str(tmp_path / "shared.db")
        store1 = EventStore(db_path=db_path, table_name="sports_events")
        store2 = EventStore(db_path=db_path, table_name="news_events")

        store1.store(_make_stored_event("goal", 0.8, "Sports event", "Detail"))
        store2.store(_make_stored_event("breaking", 0.9, "News event", "Detail"))

        assert len(store1.get_recent(limit=10)) == 1
        assert store1.get_recent(limit=10)[0]["event_type"] == "goal"
        assert len(store2.get_recent(limit=10)) == 1
        assert store2.get_recent(limit=10)[0]["event_type"] == "breaking"


class TestEventStorePersistence:
    def test_events_persist_across_store_instances(self, tmp_path) -> None:
        db_path = str(tmp_path / "events.db")
        store1 = EventStore(db_path=db_path)
        store1.store(_make_stored_event("news", 0.8, "Persisted event", "Detail"))

        store2 = EventStore(db_path=db_path)
        results = store2.get_recent(limit=10)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# BaseStateTracker tests
# ---------------------------------------------------------------------------


class SimpleStateTracker(BaseStateTracker):
    """Concrete subclass for testing — tracks dicts by 'id' key, no domain logic."""
    pass


class TestBaseStateTrackerFirstCall:
    def test_first_call_no_events(self) -> None:
        tracker = SimpleStateTracker()
        items = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]
        events = tracker.track(items, key_fn=lambda x: x["id"])
        assert events == []

    def test_first_call_stores_state(self) -> None:
        tracker = SimpleStateTracker()
        items = [{"id": "a", "value": 1}]
        tracker.track(items, key_fn=lambda x: x["id"])
        assert "a" in tracker._previous


class TestBaseStateTrackerAdded:
    def test_new_item_detected_as_added(self) -> None:
        tracker = SimpleStateTracker()
        first = [{"id": "a", "value": 1}]
        second = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]

        tracker.track(first, key_fn=lambda x: x["id"])
        events = tracker.track(second, key_fn=lambda x: x["id"])

        added = [e for e in events if e.change_type == "added"]
        assert len(added) == 1
        assert added[0].key == "b"
        assert added[0].current == {"id": "b", "value": 2}
        assert added[0].previous is None


class TestBaseStateTrackerRemoved:
    def test_missing_item_detected_as_removed(self) -> None:
        tracker = SimpleStateTracker()
        first = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]
        second = [{"id": "a", "value": 1}]

        tracker.track(first, key_fn=lambda x: x["id"])
        events = tracker.track(second, key_fn=lambda x: x["id"])

        removed = [e for e in events if e.change_type == "removed"]
        assert len(removed) == 1
        assert removed[0].key == "b"
        assert removed[0].previous == {"id": "b", "value": 2}
        assert removed[0].current is None


class TestBaseStateTrackerChanged:
    def test_changed_item_detected(self) -> None:
        tracker = SimpleStateTracker()
        first = [{"id": "a", "value": 1}]
        second = [{"id": "a", "value": 99}]

        tracker.track(first, key_fn=lambda x: x["id"])
        events = tracker.track(second, key_fn=lambda x: x["id"])

        changed = [e for e in events if e.change_type == "changed"]
        assert len(changed) == 1
        assert changed[0].key == "a"
        assert changed[0].previous == {"id": "a", "value": 1}
        assert changed[0].current == {"id": "a", "value": 99}

    def test_unchanged_item_no_event(self) -> None:
        tracker = SimpleStateTracker()
        item = {"id": "a", "value": 1}
        tracker.track([item], key_fn=lambda x: x["id"])
        events = tracker.track([item], key_fn=lambda x: x["id"])
        assert events == []


class TestBaseStateTrackerMultiple:
    def test_multiple_changes_in_one_call(self) -> None:
        tracker = SimpleStateTracker()
        first = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]
        second = [{"id": "a", "value": 99}, {"id": "c", "value": 3}]

        tracker.track(first, key_fn=lambda x: x["id"])
        events = tracker.track(second, key_fn=lambda x: x["id"])

        change_types = {e.change_type for e in events}
        keys = {e.key for e in events}

        assert "changed" in change_types   # "a" value changed
        assert "removed" in change_types   # "b" removed
        assert "added" in change_types     # "c" added
        assert "a" in keys
        assert "b" in keys
        assert "c" in keys

    def test_custom_key_function(self) -> None:
        tracker = SimpleStateTracker()
        first = [{"name": "Arsenal", "score": 0}]
        second = [{"name": "Arsenal", "score": 1}]

        tracker.track(first, key_fn=lambda x: x["name"])
        events = tracker.track(second, key_fn=lambda x: x["name"])

        changed = [e for e in events if e.change_type == "changed"]
        assert len(changed) == 1
        assert changed[0].key == "Arsenal"


class TestStateChangeEventDataclass:
    def test_state_change_event_has_timestamp(self) -> None:
        tracker = SimpleStateTracker()
        tracker.track([{"id": "a", "value": 1}], key_fn=lambda x: x["id"])
        events = tracker.track([{"id": "a", "value": 2}], key_fn=lambda x: x["id"])
        assert isinstance(events[0].timestamp, datetime)

    def test_state_change_event_fields(self) -> None:
        tracker = SimpleStateTracker()
        tracker.track([{"id": "a", "value": 1}], key_fn=lambda x: x["id"])
        events = tracker.track([{"id": "a", "value": 2}], key_fn=lambda x: x["id"])

        event = events[0]
        assert hasattr(event, "key")
        assert hasattr(event, "change_type")
        assert hasattr(event, "previous")
        assert hasattr(event, "current")
        assert hasattr(event, "timestamp")
