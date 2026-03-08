"""Generic state tracker for detecting changes between polls.

Provides:
- StateChangeEvent dataclass: a detected change (added/removed/changed)
- BaseStateTracker: in-memory tracker that compares previous vs current by key

Subclass BaseStateTracker (or use it directly) to track any list of dicts.

Usage::

    tracker = BaseStateTracker()
    changes = tracker.track(current_items, key_fn=lambda x: x["id"])
    for change in changes:
        if change.change_type == "changed":
            # handle state change
            ...

Sports-rag example (MatchStateTracker) uses this to compare match snapshots
by match ID and detect score changes, match start, and match end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StateChangeEvent dataclass
# ---------------------------------------------------------------------------


@dataclass
class StateChangeEvent:
    """A detected change between two polls of a data source.

    Attributes:
        key: The key identifying the item (e.g., match ID, flight number).
        change_type: One of "added", "removed", "changed".
        previous: The previous state dict, or None for "added" items.
        current: The current state dict, or None for "removed" items.
        timestamp: UTC time when the change was detected.
    """

    key: str
    change_type: str  # "added" | "removed" | "changed"
    previous: dict[str, Any] | None
    current: dict[str, Any] | None
    timestamp: datetime


# ---------------------------------------------------------------------------
# BaseStateTracker
# ---------------------------------------------------------------------------


class BaseStateTracker:
    """Generic in-memory state tracker.

    Compares a new list of items against the previous list (by key) and
    returns StateChangeEvent objects for each detected change.

    On the very first call, no events are emitted — the initial state is
    stored as the baseline. This prevents spurious "added" events for items
    that were already present before tracking started.

    Not thread-safe — call ``track()`` from a single background loop.

    Subclasses can override ``_on_changed()``, ``_on_added()``, or
    ``_on_removed()`` to add domain-specific filtering or enrichment.

    Usage::

        class MatchStateTracker(BaseStateTracker):
            def track(self, matches):
                # Call base tracker, then interpret raw changes as domain events
                changes = super().track(matches, key_fn=lambda m: m["id"])
                return [self._to_match_event(c) for c in changes if self._is_significant(c)]
    """

    def __init__(self) -> None:
        # Maps key -> last seen item snapshot
        self._previous: dict[str, dict[str, Any]] = {}
        self._first_call: bool = True

    def track(
        self,
        current_items: list[dict[str, Any]],
        key_fn: Callable[[dict[str, Any]], str],
    ) -> list[StateChangeEvent]:
        """Compare current items against previous state and return changes.

        On the very first call, stores the current state as baseline and
        returns an empty list (no events on first observation).

        Args:
            current_items: List of item dicts representing current state.
            key_fn: Function that extracts a unique string key from each item.

        Returns:
            List of StateChangeEvent objects for added/removed/changed items.
        """
        now = datetime.now(timezone.utc)
        current_by_key: dict[str, dict[str, Any]] = {key_fn(item): item for item in current_items}

        if self._first_call:
            self._previous = current_by_key
            self._first_call = False
            return []

        events: list[StateChangeEvent] = []

        # Check for added and changed items
        for key, curr in current_by_key.items():
            prev = self._previous.get(key)
            if prev is None:
                events.append(StateChangeEvent(
                    key=key,
                    change_type="added",
                    previous=None,
                    current=curr,
                    timestamp=now,
                ))
            elif curr != prev:
                events.append(StateChangeEvent(
                    key=key,
                    change_type="changed",
                    previous=prev,
                    current=curr,
                    timestamp=now,
                ))

        # Check for removed items
        for key, prev in self._previous.items():
            if key not in current_by_key:
                events.append(StateChangeEvent(
                    key=key,
                    change_type="removed",
                    previous=prev,
                    current=None,
                    timestamp=now,
                ))

        # Update stored state
        self._previous = current_by_key

        return events
