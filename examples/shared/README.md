# Shared: Event Detection Base Classes

Reusable base classes for building live event detection into any RAG partner example.

## The Pattern

Every live-feed partner follows the same pipeline shape:

```
Data source -> Ingest -> Embed/store -> Detect events -> Score significance -> Push to subscribers
```

The three base classes capture the generic parts of this pipeline. Subclass them and implement only the domain-specific logic.

## What to Implement (3 things)

### 1. Event detection rules (`BaseEventDetector`)

```python
from shared.base_event_detector import BaseEventDetector, Classification

class NewsEventDetector(BaseEventDetector):

    def _passes_prefilter(self, item: dict) -> bool:
        # Cheap rule check — no LLM cost
        return bool(re.search(r"breaking|urgent", item.get("title", ""), re.I))

    def _classify(self, item: dict) -> Classification | None:
        # LLM classification — only called when prefilter passes
        response = litellm.completion(
            model=self._llm_model,
            messages=[{"role": "user", "content": item["title"]}],
        )
        parsed = json.loads(response.choices[0].message.content)
        return Classification(
            event_type=parsed["event_type"],
            significance=float(parsed["significance"]),
            summary=parsed["summary"],
            detail=parsed["detail"],
        )
```

Call `detector.detect(items)` to run the full pipeline: prefilter -> dedup -> classify -> threshold.

### 2. State tracking (`BaseStateTracker`)

For structured data sources (APIs with state you can diff):

```python
from shared.base_state_tracker import BaseStateTracker

tracker = BaseStateTracker()

# First call: stores baseline, returns []
tracker.track(flights, key_fn=lambda f: f["flight_number"])

# Subsequent calls: returns added/removed/changed events
changes = tracker.track(flights, key_fn=lambda f: f["flight_number"])
for change in changes:
    print(change.change_type, change.key, change.previous, change.current)
```

Subclass to add domain logic:

```python
class FlightStateTracker(BaseStateTracker):
    def track(self, flights):
        changes = super().track(flights, key_fn=lambda f: f["flight_number"])
        return [self._to_flight_event(c) for c in changes if self._is_significant(c)]
```

### 3. Persistent storage (`EventStore`)

Generic SQLite store — no subclassing needed:

```python
from shared.base_event_store import EventStore, StoredEvent

store = EventStore(db_path="events.db", table_name="news_events")

event_id = store.store(StoredEvent(
    event_type="breaking_news",
    significance=0.9,
    summary="Breaking: something happened",
    detail="Full context here.",
    card={"type": "news_card", "title": "Breaking News"},
    source_items=[article],
    timestamp=datetime.now(timezone.utc),
    content_hash="sha256-of-article-url-and-title",
))

recent = store.get_recent(limit=10)
filtered = store.query(event_type="breaking_news", since=cutoff)
```

The `table_name` parameter lets multiple domains share one DB file:

```python
sports_store = EventStore(db_path="events.db", table_name="sports_events")
news_store   = EventStore(db_path="events.db", table_name="news_events")
travel_store = EventStore(db_path="events.db", table_name="travel_events")
```

## Adding a New Domain: Step by Step

1. Create `examples/webhook/my-domain/python/`

2. Create `event_detector.py`:
   ```python
   from shared.base_event_detector import BaseEventDetector, Classification

   class MyEventDetector(BaseEventDetector):
       def _passes_prefilter(self, item): ...
       def _classify(self, item): ...
   ```

3. Create `event_store.py` (optionally extend for domain-specific filters):
   ```python
   from shared.base_event_store import EventStore
   # Use directly, or subclass to add domain-specific query filters
   ```

4. Create `state_tracker.py` if your data source is a diffable API:
   ```python
   from shared.base_state_tracker import BaseStateTracker

   class MyStateTracker(BaseStateTracker):
       def track(self, items):
           changes = super().track(items, key_fn=lambda x: x["id"])
           return [self._to_domain_event(c) for c in changes]
   ```

5. Wire into your background loop:
   ```python
   detector = MyEventDetector(llm_model="vertex_ai/gemini-2.5-flash", significance_threshold=0.5)
   store = EventStore(db_path="events.db", table_name="my_events")

   async def detection_loop():
       while True:
           items = await fetch_my_data()
           events = detector.detect(items)
           for event in events:
               store.store(StoredEvent(...))
               # POST to Nexo notify endpoint
           await asyncio.sleep(60)
   ```

## Reference: sports-rag

`examples/webhook/sports-rag/python/` is the reference implementation:

| File | Role |
|---|---|
| `match_state.py` | `MatchStateTracker(BaseStateTracker)` — diffs match API responses |
| `event_detector.py` | `EventDetector(BaseEventDetector)` — keyword prefilter + LLM for articles |
| `event_store.py` | `EventStore(_BaseEventStore)` — adds `team` filter for sports queries |

## Running Tests

```bash
# Base class tests
cd examples/shared
pytest test_base_event_detection.py -v

# Sports-rag tests (must still pass after any base class changes)
cd examples/webhook/sports-rag/python
pytest test_event_detection.py test_sports_rag.py test_event_wiring.py -v
```
