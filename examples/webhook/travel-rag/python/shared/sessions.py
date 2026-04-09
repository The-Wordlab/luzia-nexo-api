"""Lightweight DB-backed session store keyed by thread_id.

Requires a PostgreSQL database with a sessions table:
    CREATE TABLE IF NOT EXISTS sessions (
        thread_id TEXT PRIMARY KEY,
        state JSONB NOT NULL DEFAULT '{}',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

Usage:
    store = SessionStore(database_url)
    await store.init()  # creates table if needed

    session = await store.get(thread_id)           # returns {} for new
    await store.update(thread_id, cart=items)       # merges into state
    await store.add_turn(thread_id, "user", "Hi")   # appends to history
    history = await store.get_history(thread_id, 10) # last N turns
"""

from __future__ import annotations

import json
import logging

import asyncpg

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    thread_id TEXT PRIMARY KEY,
    state JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class SessionStore:
    """Database-backed session store for Cloud Run webhook servers.

    Cloud Run instances are ephemeral - in-memory state is lost between
    requests on different instances. This store persists conversation state
    in PostgreSQL so any instance can continue a session.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        """Create connection pool and ensure sessions table exists."""
        self._pool = await asyncpg.create_pool(self._database_url)
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)
        logger.info("SessionStore initialised")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _pool_required(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("SessionStore.init() has not been called")
        return self._pool

    async def get(self, thread_id: str) -> dict:
        """Return session state for thread_id, or {} if it does not exist."""
        pool = self._pool_required()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM sessions WHERE thread_id = $1",
                thread_id,
            )
        if row is None:
            return {}
        state = row["state"]
        if isinstance(state, str):
            return json.loads(state)
        return dict(state)

    async def update(self, thread_id: str, **kwargs) -> dict:
        """Merge kwargs into the session state and persist.

        Uses an UPSERT so new sessions are created automatically.
        Returns the updated state.
        """
        pool = self._pool_required()
        patch = json.dumps(kwargs)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO sessions (thread_id, state, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (thread_id) DO UPDATE
                    SET state = sessions.state || $2::jsonb,
                        updated_at = NOW()
                RETURNING state
                """,
                thread_id,
                patch,
            )
        state = row["state"]
        if isinstance(state, str):
            return json.loads(state)
        return dict(state)

    async def add_turn(self, thread_id: str, role: str, content: str) -> None:
        """Append a conversation turn to state["history"].

        Fetches the current state, appends the turn, and writes back.
        This is not atomic but is safe for single-user conversation threads.
        """
        pool = self._pool_required()
        turn = {"role": role, "content": content}
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM sessions WHERE thread_id = $1",
                thread_id,
            )
            if row is None:
                current: dict = {}
            else:
                state_val = row["state"]
                current = (
                    json.loads(state_val)
                    if isinstance(state_val, str)
                    else dict(state_val)
                )

            history: list = current.get("history", [])
            history.append(turn)
            current["history"] = history

            await conn.execute(
                """
                INSERT INTO sessions (thread_id, state, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (thread_id) DO UPDATE
                    SET state = $2::jsonb,
                        updated_at = NOW()
                """,
                thread_id,
                json.dumps(current),
            )

    async def get_history(self, thread_id: str, max_turns: int = 10) -> list[dict]:
        """Return the last max_turns turns from state["history"]."""
        state = await self.get(thread_id)
        history: list = state.get("history", [])
        return history[-max_turns:] if len(history) > max_turns else history
