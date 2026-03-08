"""Match state tracker for detecting score changes, match start, and match end.

MatchStateTracker is a thin domain subclass of BaseStateTracker that converts
generic StateChangeEvent objects into MatchEvent objects with sports-specific
significance scores and descriptions.

The base tracker handles:
- In-memory state storage
- First-call no-events semantics
- Added/removed/changed diffing by key

MatchStateTracker adds:
- Interpreting "changed" events as score_change / match_start / match_end
- Significance scoring per event type
- Human-readable description builders
"""

from __future__ import annotations

import logging
import sys
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Allow importing from the shared directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared"))

from base_state_tracker import BaseStateTracker, StateChangeEvent

logger = logging.getLogger(__name__)

# Significance scores per event type
SIGNIFICANCE_SCORE_CHANGE = 0.8
SIGNIFICANCE_EQUALISER = 0.9
SIGNIFICANCE_MATCH_START = 0.5
SIGNIFICANCE_MATCH_END = 0.7

# Statuses that indicate a match is underway
_IN_PLAY_STATUSES = {"IN_PLAY", "PAUSED", "HALFTIME"}
# Statuses that indicate a match is finished
_FINISHED_STATUSES = {"FINISHED", "AWARDED"}
# Statuses that indicate a match has not started yet
_PRE_MATCH_STATUSES = {"SCHEDULED", "TIMED", "POSTPONED", "SUSPENDED", "CANCELLED"}


@dataclass
class MatchEvent:
    """A detected match event (score change, match start, or match end)."""

    event_type: str  # "score_change" | "match_start" | "match_end"
    significance: float  # 0.0 – 1.0
    match_data: dict[str, Any]  # the current match snapshot
    description: str  # human-readable description
    timestamp: datetime


class MatchStateTracker(BaseStateTracker):
    """Tracks previous match states and emits MatchEvent objects on changes.

    Delegates state diffing to BaseStateTracker, then converts generic
    StateChangeEvent objects into domain-specific MatchEvent objects.

    All state is stored in memory (dict keyed by match ID). Not thread-safe —
    call ``track()`` from a single background loop.
    """

    def track(self, current_matches: list[dict[str, Any]]) -> list[MatchEvent]:
        """Compare current match states against previous and return detected events.

        On the very first call there are no previous states, so no events are
        emitted (we don't want to fire "match started" for games that were
        already in play before we first polled).

        Args:
            current_matches: List of match dicts, each with at least:
                ``id``, ``home_team``, ``away_team``, ``home_score``,
                ``away_score``, ``status``.

        Returns:
            List of MatchEvent objects, one per detected change.
        """
        now = datetime.now(timezone.utc)
        changes = super().track(current_matches, key_fn=lambda m: m["id"])

        events: list[MatchEvent] = []
        for change in changes:
            if change.change_type == "changed" and change.previous is not None and change.current is not None:
                events.extend(self._diff(change.previous, change.current, now))

        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _diff(
        self,
        prev: dict[str, Any],
        curr: dict[str, Any],
        now: datetime,
    ) -> list[MatchEvent]:
        """Return all events detected by comparing previous vs current state."""
        events: list[MatchEvent] = []

        prev_status = prev.get("status", "")
        curr_status = curr.get("status", "")

        # Match start: transitioned from pre-match to in-play
        if prev_status in _PRE_MATCH_STATUSES and curr_status in _IN_PLAY_STATUSES:
            events.append(
                MatchEvent(
                    event_type="match_start",
                    significance=SIGNIFICANCE_MATCH_START,
                    match_data=curr,
                    description=_start_description(curr),
                    timestamp=now,
                )
            )

        # Score change
        prev_home = int(prev.get("home_score", 0))
        prev_away = int(prev.get("away_score", 0))
        curr_home = int(curr.get("home_score", 0))
        curr_away = int(curr.get("away_score", 0))

        if (curr_home, curr_away) != (prev_home, prev_away):
            is_equaliser = curr_home == curr_away and (curr_home > prev_home or curr_away > prev_away)
            significance = SIGNIFICANCE_EQUALISER if is_equaliser else SIGNIFICANCE_SCORE_CHANGE
            events.append(
                MatchEvent(
                    event_type="score_change",
                    significance=significance,
                    match_data=curr,
                    description=_score_description(curr, is_equaliser=is_equaliser),
                    timestamp=now,
                )
            )

        # Match end: transitioned to finished
        if prev_status not in _FINISHED_STATUSES and curr_status in _FINISHED_STATUSES:
            events.append(
                MatchEvent(
                    event_type="match_end",
                    significance=SIGNIFICANCE_MATCH_END,
                    match_data=curr,
                    description=_end_description(curr),
                    timestamp=now,
                )
            )

        return events


# ---------------------------------------------------------------------------
# Description builders
# ---------------------------------------------------------------------------


def _score_description(match: dict[str, Any], *, is_equaliser: bool = False) -> str:
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    hs = int(match.get("home_score", 0))
    aws = int(match.get("away_score", 0))
    score = f"{hs}-{aws}"
    competition = match.get("competition", "")
    prefix = f"[{competition}] " if competition else ""
    if is_equaliser:
        return f"{prefix}{home} {score} {away} — equaliser!"
    return f"{prefix}{home} {score} {away} — score change"


def _start_description(match: dict[str, Any]) -> str:
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    competition = match.get("competition", "")
    prefix = f"[{competition}] " if competition else ""
    return f"{prefix}{home} vs {away} — match started"


def _end_description(match: dict[str, Any]) -> str:
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    hs = int(match.get("home_score", 0))
    aws = int(match.get("away_score", 0))
    score = f"{hs}-{aws}"
    competition = match.get("competition", "")
    prefix = f"[{competition}] " if competition else ""
    return f"{prefix}{home} {score} {away} — full time"
