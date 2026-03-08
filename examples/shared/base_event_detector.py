"""Abstract base class for event detection pipelines.

Provides:
- Event dataclass: the output of detection (type, significance, summary, detail, card, ...)
- Classification dataclass: raw LLM output before thresholding
- BaseEventDetector: abstract class with shared dedup logic

Subclass and implement:
    _passes_prefilter(item) -> bool     fast rule-based check (no LLM cost)
    _classify(item) -> Classification | None   LLM or domain-logic classification
"""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Classification:
    """Raw LLM/domain classification result before significance thresholding."""

    event_type: str  # domain-specific type string
    significance: float  # 0.0 – 1.0
    summary: str  # 1-sentence
    detail: str  # 2-3 sentences
    card: dict[str, Any] | None = None  # optional Nexo card envelope


@dataclass
class Event:
    """A fully detected event ready to be stored and dispatched."""

    event_type: str
    significance: float
    summary: str
    detail: str
    card: dict[str, Any] | None
    source_items: list[Any]
    timestamp: datetime
    content_hash: str  # sha256 hex; used for dedup
    teams: list[str] = field(default_factory=list)

    def _replace(self, **kwargs: Any) -> "Event":
        """Return a copy with updated fields (namedtuple-style)."""
        from dataclasses import replace
        return replace(self, **kwargs)


# ---------------------------------------------------------------------------
# Base detector
# ---------------------------------------------------------------------------


class BaseEventDetector(ABC):
    """Abstract two-stage event detector: rule prefilter + classification.

    Concrete subclasses must implement:
        _passes_prefilter(item) -> bool
        _classify(item) -> Classification | None

    The base class provides:
    - Content-hash dedup (``_seen_hashes`` dict, in-memory)
    - Significance threshold filtering
    - ``detect(items)`` which orchestrates the full pipeline

    Usage::

        class NewsEventDetector(BaseEventDetector):
            def _passes_prefilter(self, item):
                return bool(re.search(r"breaking|urgent", item.get("title", ""), re.I))

            def _classify(self, item):
                # call LLM, return Classification or None on failure
                ...
    """

    def __init__(
        self,
        llm_model: str = "ollama/llama3.2",
        significance_threshold: float = 0.5,
    ) -> None:
        self._llm_model = llm_model
        self._threshold = significance_threshold
        # In-memory dedup: content_hash -> True
        self._seen_hashes: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, items: list[dict[str, Any]]) -> list[Event]:
        """Run the detection pipeline over a list of raw items.

        Each item goes through:
        1. Content-hash dedup (skip if seen before)
        2. ``_passes_prefilter()`` (cheap rule check)
        3. ``_classify()`` (LLM/domain logic)
        4. Significance threshold check

        Args:
            items: List of raw data items (article dicts, match snapshots, etc.)

        Returns:
            List of Event objects that passed all stages.
        """
        events: list[Event] = []
        for item in items:
            event = self._process_item(item)
            if event is not None:
                events.append(event)
        return events

    # ------------------------------------------------------------------
    # Abstract methods (subclass must implement)
    # ------------------------------------------------------------------

    @abstractmethod
    def _passes_prefilter(self, item: dict[str, Any]) -> bool:
        """Return True if this item should proceed to classification.

        This is a cheap rule-based check (keyword matching, freshness, etc.).
        No LLM call should be made here.
        """

    @abstractmethod
    def _classify(self, item: dict[str, Any]) -> Classification | None:
        """Classify an item using LLM or domain logic.

        Return a Classification, or None on failure or if item is not significant.
        """

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_item(self, item: dict[str, Any]) -> Event | None:
        """Run a single item through the full pipeline."""
        content_hash = self._compute_hash(item)

        if content_hash in self._seen_hashes:
            return None

        if not self._passes_prefilter(item):
            # Don't mark as seen — a future call might see this item after a
            # state change that makes it pass the prefilter.
            return None

        # Mark seen before classifying to prevent concurrent re-processing
        self._seen_hashes[content_hash] = True

        classification = self._classify(item)
        if classification is None:
            return None

        if classification.significance < self._threshold:
            return None

        return Event(
            event_type=classification.event_type,
            significance=classification.significance,
            summary=classification.summary,
            detail=classification.detail,
            card=classification.card,
            source_items=[item],
            timestamp=datetime.now(timezone.utc),
            content_hash=content_hash,
        )

    def _compute_hash(self, item: dict[str, Any]) -> str:
        """Produce a stable content hash for any item dict.

        Uses 'link' + 'title' if present (article-style), otherwise JSON-encodes
        the whole item with sorted keys for determinism.
        """
        link = item.get("link", "")
        title = item.get("title", "")
        if link or title:
            key = f"{link}:{title}"
        else:
            key = json.dumps(item, sort_keys=True, default=str)
        return hashlib.sha256(key.encode()).hexdigest()
