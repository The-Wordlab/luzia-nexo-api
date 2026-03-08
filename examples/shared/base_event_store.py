"""Generic SQLite-backed event store.

Provides:
- store(event) -> event_id  (deduplicates by content_hash)
- query(event_type, since, limit) -> list of dicts
- get_recent(limit) -> list of dicts (newest first)

The table name is configurable so multiple domains can coexist in the same DB.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StoredEvent dataclass (mirrors Event from base_event_detector)
# ---------------------------------------------------------------------------


@dataclass
class StoredEvent:
    """An event ready to be persisted in the EventStore."""

    event_type: str
    significance: float
    summary: str
    detail: str
    card: dict[str, Any] | None
    source_items: list[Any]
    timestamp: datetime
    content_hash: str
    teams: list[str] = field(default_factory=list)

    def _replace(self, **kwargs: Any) -> "StoredEvent":
        from dataclasses import replace
        return replace(self, **kwargs)


# ---------------------------------------------------------------------------
# SQL templates (parameterised by table name at __init__ time)
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {table} (
    event_id     TEXT PRIMARY KEY,
    content_hash TEXT UNIQUE NOT NULL,
    event_type   TEXT NOT NULL,
    significance REAL NOT NULL,
    summary      TEXT NOT NULL,
    detail       TEXT NOT NULL,
    teams_json   TEXT NOT NULL DEFAULT '[]',
    card_json    TEXT,
    timestamp    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_{table}_type      ON {table} (event_type);
CREATE INDEX IF NOT EXISTS idx_{table}_timestamp ON {table} (timestamp DESC);
"""

_INSERT_SQL_TEMPLATE = """
INSERT OR IGNORE INTO {table}
    (event_id, content_hash, event_type, significance, summary, detail, teams_json, card_json, timestamp)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_BY_HASH_SQL_TEMPLATE = "SELECT event_id FROM {table} WHERE content_hash = ? LIMIT 1"


# ---------------------------------------------------------------------------
# EventStore
# ---------------------------------------------------------------------------


class EventStore:
    """Generic SQLite-backed persistent store for detected events.

    Deduplicates by ``content_hash`` — calling ``store()`` twice with the same
    hash returns the original ``event_id`` and does not insert a duplicate row.

    The ``table_name`` parameter allows multiple domains to share one DB file
    (e.g., sports events + news events in one ``events.db``).

    Thread safety: each method opens and closes a connection. Suitable for
    single-writer, single-reader scenarios (background ingest loop).

    Usage::

        store = EventStore(db_path="events.db", table_name="sports_events")
        event_id = store.store(stored_event)
        recent = store.get_recent(limit=10)
    """

    def __init__(
        self,
        db_path: str = "events.db",
        table_name: str = "events",
    ) -> None:
        self._db_path = db_path
        self._table = table_name
        self._create_sql = _CREATE_TABLE_SQL_TEMPLATE.format(table=self._table)
        self._insert_sql = _INSERT_SQL_TEMPLATE.format(table=self._table)
        self._select_by_hash_sql = _SELECT_BY_HASH_SQL_TEMPLATE.format(table=self._table)
        self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, event: StoredEvent) -> str:
        """Persist an event. Returns the event_id (existing if deduped).

        Args:
            event: StoredEvent instance to persist.

        Returns:
            str: The event_id (newly generated or existing for duplicates).
        """
        with self._connect() as conn:
            row = conn.execute(self._select_by_hash_sql, (event.content_hash,)).fetchone()
            if row:
                return row[0]

            event_id = str(uuid.uuid4())
            timestamp_str = _to_iso(event.timestamp)
            teams_json = json.dumps(event.teams)
            card_json = json.dumps(event.card) if event.card is not None else None

            conn.execute(
                self._insert_sql,
                (
                    event_id,
                    event.content_hash,
                    event.event_type,
                    event.significance,
                    event.summary,
                    event.detail,
                    teams_json,
                    card_json,
                    timestamp_str,
                ),
            )
            conn.commit()
            logger.debug("Stored event %s (%s) in table %s", event_id, event.event_type, self._table)
            return event_id

    def query(
        self,
        *,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query stored events with optional filters.

        Args:
            event_type: Filter by event type (e.g. "goal", "breaking_news").
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

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent events, newest first.

        Args:
            limit: Maximum number of results.

        Returns:
            List of event dicts.
        """
        return self.query(limit=limit)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._create_sql)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _to_iso(dt: datetime) -> str:
    """Serialize datetime to ISO-8601 string with timezone info."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["teams"] = json.loads(d.pop("teams_json", "[]"))
    card_json = d.pop("card_json", None)
    d["card"] = json.loads(card_json) if card_json else None
    return d
