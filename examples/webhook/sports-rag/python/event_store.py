"""Sports-specific SQLite event store.

Thin subclass of the shared EventStore that adds a ``team`` filter to
``query()`` — teams are stored as a JSON array and filtered via LIKE.

Everything else (storage, dedup, persistence, table init) is inherited
from the generic EventStore in examples/shared/base_event_store.py.
"""

from __future__ import annotations

import sys
import os
import logging
from datetime import datetime
from typing import Any

# Allow importing from the shared directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared"))

from base_event_store import EventStore as _BaseEventStore, StoredEvent, _to_iso, _row_to_dict

# Re-export DetectedEvent alias so existing imports still work
from event_detector import DetectedEvent

logger = logging.getLogger(__name__)


class EventStore(_BaseEventStore):
    """SQLite-backed persistent store for sports DetectedEvent objects.

    Extends the generic EventStore with a ``team`` filter on query().
    All other behaviour (dedup, persistence, table init) is inherited.

    Deduplicates by ``content_hash`` — calling ``store()`` twice with the same
    hash returns the original ``event_id`` and does not insert a duplicate row.
    """

    def query(
        self,
        *,
        event_type: str | None = None,
        team: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query stored events with optional filters.

        Args:
            event_type: Filter by event type (e.g. "goal", "match_start").
            team: Filter to events involving this team name (JSON array substring).
            since: Only return events after this datetime.
            limit: Maximum number of results to return (default 50).

        Returns:
            List of event dicts, newest first.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)

        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(_to_iso(since))

        if team is not None:
            # teams_json is a JSON array — use LIKE for a simple substring search
            conditions.append("teams_json LIKE ?")
            params.append(f'%"{team}"%')

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT event_id, content_hash, event_type, significance, summary, detail,
                   teams_json, card_json, timestamp
            FROM {self._table}
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [_row_to_dict(row) for row in rows]
