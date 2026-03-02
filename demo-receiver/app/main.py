from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel


DEMO_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


@dataclass
class EventRecord:
    event_id: str
    received_at: int
    payload: dict[str, Any]


class InMemoryEventStore:
    """Small in-memory store for demo receiver events.

    This is intentionally minimal for the bootstrap sprint.
    Replace with Firestore-backed implementation in a later slice.
    """

    def __init__(self, max_events_per_key: int = 200, ttl_seconds: int = 86400):
        self.max_events_per_key = max_events_per_key
        self.ttl_seconds = ttl_seconds
        self._events: dict[str, deque[EventRecord]] = defaultdict(deque)
        self._lock = Lock()

    def append(self, demo_key: str, event: EventRecord) -> None:
        with self._lock:
            q = self._events[demo_key]
            q.append(event)
            while len(q) > self.max_events_per_key:
                q.popleft()
            self._evict_expired_locked(q)

    def list_recent(self, demo_key: str, limit: int) -> list[EventRecord]:
        with self._lock:
            q = self._events.get(demo_key)
            if q is None:
                return []
            self._evict_expired_locked(q)
            return list(q)[-limit:][::-1]

    def _evict_expired_locked(self, q: deque[EventRecord]) -> None:
        cutoff = int(time.time()) - self.ttl_seconds
        while q and q[0].received_at < cutoff:
            q.popleft()


class IngestResponse(BaseModel):
    status: str = "accepted"
    event_id: str


class EventResponse(BaseModel):
    event_id: str
    received_at: int
    payload: dict[str, Any]


class EventsListResponse(BaseModel):
    demo_key: str
    count: int
    events: list[EventResponse]


class HealthResponse(BaseModel):
    ok: bool = True
    storage: str = "in_memory"


app = FastAPI(title="nexo-examples-py demo receiver")
store = InMemoryEventStore(
    max_events_per_key=int(os.getenv("MAX_EVENTS_PER_KEY", "200")),
    ttl_seconds=int(os.getenv("EVENT_TTL_SECONDS", "86400")),
)


def _validate_demo_key(demo_key: str) -> None:
    if not DEMO_KEY_RE.fullmatch(demo_key):
        raise HTTPException(status_code=400, detail="Invalid demo_key format")


def _safe_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"_raw": str(raw)[:2000]}

    # Minimal redaction guardrails for known sensitive fields.
    redacted = dict(raw)
    for key in list(redacted.keys()):
        k = key.lower()
        if "secret" in k or "token" in k or "authorization" in k:
            redacted[key] = "[REDACTED]"
    return redacted


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/v1/ingest/{demo_key}", response_model=IngestResponse)
async def ingest_event(demo_key: str, request: Request) -> IngestResponse:
    _validate_demo_key(demo_key)

    payload = _safe_payload(await request.json())
    event_id = f"evt_{int(time.time() * 1000)}"
    received_at = int(time.time())
    store.append(
        demo_key,
        EventRecord(event_id=event_id, received_at=received_at, payload=payload),
    )
    return IngestResponse(event_id=event_id)


@app.get("/v1/events/{demo_key}", response_model=EventsListResponse)
async def list_events(
    demo_key: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> EventsListResponse:
    _validate_demo_key(demo_key)
    events = store.list_recent(demo_key, limit=limit)
    return EventsListResponse(
        demo_key=demo_key,
        count=len(events),
        events=[
            EventResponse(
                event_id=e.event_id,
                received_at=e.received_at,
                payload=e.payload,
            )
            for e in events
        ],
    )
