"""Event detector: two-stage (rule-based prefilter + LLM classification) pipeline.

EventDetector extends BaseEventDetector for sports-specific detection:
- Article path: keyword prefilter + LLM classification
- Match state path: evaluate_match_event() bypasses LLM entirely

DetectedEvent is an alias for the shared Event dataclass (backward compat).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

# Allow importing from the shared directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared"))

from base_event_detector import BaseEventDetector, Classification, Event

from match_state import MatchEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DetectedEvent = shared Event (backward compatibility alias)
# ---------------------------------------------------------------------------

DetectedEvent = Event

# ---------------------------------------------------------------------------
# Keywords for rule-based article prefilter
# ---------------------------------------------------------------------------

_SIGNIFICANT_KEYWORDS = re.compile(
    r"\b("
    r"goal|goals|scored|scorer|scorers|"
    r"red.?card|sent.?off|penalty|penalties|"
    r"breaking|transfer|signing|signed|confirmed|"
    r"injury|injured|ruled.?out|crisis|comeback|"
    r"winner|winner|equaliser|equalizer|"
    r"hat.?trick|brace|record|debut|"
    r"manager|sacked|appointed|resigned|"
    r"last.?minute|stoppage.?time|injury.?time|"
    r"fire|crucial|dramatic|shock|upset|thrash"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# LLM prompt for article classification
# ---------------------------------------------------------------------------

_CLASSIFICATION_SYSTEM_PROMPT = """You are a sports news editor deciding whether an article is worth immediately notifying football fans.

Classify the article and respond with ONLY a valid JSON object (no markdown, no explanation):
{
  "event_type": "<goal|red_card|transfer|breaking_news|match_result|injury|manager_news|routine>",
  "significance": <float 0.0-1.0>,
  "summary": "<1 sentence summary>",
  "detail": "<2-3 sentence detailed description>"
}

Significance guide:
- 0.9-1.0: Breaking news, last-minute goals, red cards in decisive moments, confirmed transfers
- 0.7-0.8: Regular goals, significant injury news, manager sacked/appointed
- 0.5-0.6: Transfer rumours, squad updates, preview analysis
- 0.3-0.4: Minor injuries, routine news
- 0.0-0.2: Scheduled fixtures, mundane previews, already known information

Respond with ONLY the JSON object."""


# ---------------------------------------------------------------------------
# EventDetector
# ---------------------------------------------------------------------------


class EventDetector(BaseEventDetector):
    """Sports-specific two-stage event detector.

    Match state events (score_change, match_start, match_end) bypass the LLM —
    use evaluate_match_event() for those.

    Articles from RSS feeds go through the standard BaseEventDetector pipeline:
    1. ``_passes_prefilter()``: fast keyword check (no cost)
    2. ``_classify()``: LLM classification (only if prefilter passes)

    Both paths produce DetectedEvent (= shared Event) objects. Dedup is done
    by content_hash — seen hashes are stored in-memory and skipped.
    """

    def __init__(
        self,
        llm_model: str = "vertex_ai/gemini-2.5-flash",
        significance_threshold: float = 0.5,
    ) -> None:
        super().__init__(llm_model=llm_model, significance_threshold=significance_threshold)

    # ------------------------------------------------------------------
    # Match event path (no LLM) — kept separate from article pipeline
    # ------------------------------------------------------------------

    def evaluate_match_event(self, event: MatchEvent) -> DetectedEvent | None:
        """Convert a MatchEvent into a DetectedEvent, or None if below threshold.

        No LLM is called — the significance score is already determined by the
        MatchStateTracker rules.
        """
        if event.significance < self._threshold:
            return None

        content_hash = _hash_match_event(event)
        if content_hash in self._seen_hashes:
            return None

        detected = DetectedEvent(
            event_type=event.event_type,
            significance=event.significance,
            summary=event.description,
            detail=event.description,
            card=_match_event_to_card(event),
            source_items=[event],
            timestamp=event.timestamp,
            content_hash=content_hash,
            teams=_teams_from_match(event.match_data),
        )
        self._seen_hashes[content_hash] = True
        return detected

    # ------------------------------------------------------------------
    # Article path (LLM) — implements BaseEventDetector abstract methods
    # ------------------------------------------------------------------

    def _passes_prefilter(self, article: dict[str, Any]) -> bool:
        """Return True if the article contains keywords suggesting significance."""
        text = f"{article.get('title', '')} {article.get('text', '')}"
        return bool(_SIGNIFICANT_KEYWORDS.search(text))

    def _classify(self, article: dict[str, Any]) -> Classification | None:
        """Run LLM classification on an article."""
        user_content = (
            f"Title: {article.get('title', '')}\n"
            f"Text: {article.get('text', '')[:800]}\n"
            f"Published: {article.get('published', '')}"
        )

        try:
            response = litellm.completion(
                model=self._llm_model,
                messages=[
                    {"role": "system", "content": _CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=200,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("LLM classification failed for article %r: %s", article.get("title", ""), exc)
            return None

        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                logger.warning("Could not parse LLM classification response: %r", raw[:200])
                return None
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Could not parse extracted JSON from LLM response")
                return None

        return Classification(
            event_type=str(parsed.get("event_type", "unknown")),
            significance=float(parsed.get("significance", 0.0)),
            summary=str(parsed.get("summary", "")),
            detail=str(parsed.get("detail", "")),
        )

    # ------------------------------------------------------------------
    # Backward-compat aliases used by existing tests
    # ------------------------------------------------------------------

    def _passes_article_prefilter(self, article: dict[str, Any]) -> bool:
        """Backward-compat alias for _passes_prefilter."""
        return self._passes_prefilter(article)

    def classify_article(self, article: dict[str, Any]) -> DetectedEvent | None:
        """Run LLM classification on an article (backward-compat wrapper).

        Returns None if:
        - The content hash has already been seen (dedup)
        - The LLM returns significance below threshold
        - The LLM call fails
        """
        results = self.detect([article])
        return results[0] if results else None


# ---------------------------------------------------------------------------
# Hash helpers (kept for backward compat; base class computes hash for articles)
# ---------------------------------------------------------------------------


def _hash_match_event(event: MatchEvent) -> str:
    """Produce a stable content hash for a MatchEvent."""
    match = event.match_data
    key = (
        f"{event.event_type}:"
        f"{match.get('id', '')}:"
        f"{match.get('home_score', 0)}-{match.get('away_score', 0)}:"
        f"{match.get('status', '')}"
    )
    return hashlib.sha256(key.encode()).hexdigest()


def _teams_from_match(match: dict[str, Any]) -> list[str]:
    teams = []
    if match.get("home_team"):
        teams.append(match["home_team"])
    if match.get("away_team"):
        teams.append(match["away_team"])
    return teams


def _match_event_to_card(event: MatchEvent) -> dict[str, Any] | None:
    """Build a minimal Nexo card envelope for a match event."""
    match = event.match_data
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    hs = int(match.get("home_score", 0))
    aws = int(match.get("away_score", 0))
    competition = match.get("competition", "")

    if event.event_type == "score_change":
        return {
            "type": "match_result",
            "title": f"{home} {hs}-{aws} {away}",
            "subtitle": competition,
            "badges": [competition, "Live"] if match.get("status") != "FINISHED" else [competition, "Full Time"],
            "fields": [
                {"label": "Date", "value": str(match.get("date", ""))},
            ],
            "metadata": {"capability_state": "live"},
        }
    if event.event_type == "match_start":
        return {
            "type": "match_result",
            "title": f"{home} vs {away}",
            "subtitle": f"{competition} — Kick off!",
            "badges": [competition, "Live"],
            "fields": [],
            "metadata": {"capability_state": "live"},
        }
    if event.event_type == "match_end":
        return {
            "type": "match_result",
            "title": f"{home} {hs}-{aws} {away}",
            "subtitle": f"{competition} — Full Time",
            "badges": [competition, "FT"],
            "fields": [],
            "metadata": {"capability_state": "live"},
        }
    return None
