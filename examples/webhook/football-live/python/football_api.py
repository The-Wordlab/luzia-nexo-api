"""Football-data.org API client — pure, injectable, testable."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

COMPETITIONS: dict[str, str] = {
    "PL": "Premier League",
    "PD": "La Liga",
    "BSA": "Brasileirão",
}

DEFAULT_BASE_URL = "https://api.football-data.org/v4"


class FootballDataClient:
    """Thin wrapper around football-data.org v4 API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client(
            headers={"X-Auth-Token": api_key},
            timeout=15.0,
        )

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    def fetch_matches(
        self,
        competition: str,
        status: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent matches for a competition code (PL, PD, BSA).

        Returns normalised flat dicts.  Empty list on error.
        """
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        try:
            resp = self._client.get(
                f"{self.base_url}/competitions/{competition}/matches",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("fetch_matches(%s) failed: %s", competition, exc)
            return []

        comp_name = COMPETITIONS.get(competition, competition)
        return [self._normalise_match(m, comp_name, competition) for m in data.get("matches", [])]

    def _normalise_match(self, m: dict, comp_name: str, comp_id: str) -> dict[str, Any]:
        score = m.get("score", {})
        full_time = score.get("fullTime", {})
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})

        home_score = full_time.get("home")
        away_score = full_time.get("away")

        # Extract goal scorers from the goals array
        goals = self._extract_goals(m.get("goals", []))

        # Live minute from the match minute field
        live_minute = m.get("minute")

        return {
            "id": f"match-{m.get('id', 'unknown')}",
            "home_team": home.get("name", "Unknown"),
            "away_team": away.get("name", "Unknown"),
            "home_score": home_score if home_score is not None else 0,
            "away_score": away_score if away_score is not None else 0,
            "competition": comp_name,
            "competition_id": comp_id,
            "matchday": m.get("matchday", 0),
            "date": m.get("utcDate", ""),
            "venue": m.get("venue", ""),
            "status": m.get("status", "SCHEDULED"),
            "goals": goals,
            "live_minute": live_minute,
        }

    @staticmethod
    def _extract_goals(goals: list[dict]) -> str:
        """Build a human-readable goal string from the API goals array."""
        if not goals:
            return ""
        parts: list[str] = []
        for g in goals:
            scorer = g.get("scorer", {})
            name = scorer.get("name", "Unknown") if isinstance(scorer, dict) else str(scorer)
            minute = g.get("minute", "?")
            parts.append(f"{name} {minute}'")
        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Standings
    # ------------------------------------------------------------------

    def fetch_standings(self, competition: str) -> list[dict[str, Any]]:
        """Fetch current standings for a competition code.

        Returns normalised position dicts.  Empty list on error.
        """
        try:
            resp = self._client.get(
                f"{self.base_url}/competitions/{competition}/standings",
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("fetch_standings(%s) failed: %s", competition, exc)
            return []

        comp_name = COMPETITIONS.get(competition, competition)
        standings_list: list[dict[str, Any]] = []

        for table_group in data.get("standings", []):
            if table_group.get("type") != "TOTAL":
                continue
            for entry in table_group.get("table", []):
                team = entry.get("team", {})
                standings_list.append({
                    "position": entry.get("position", 0),
                    "team": team.get("name", "Unknown"),
                    "played": entry.get("playedGames", 0),
                    "won": entry.get("won", 0),
                    "drawn": entry.get("draw", 0),
                    "lost": entry.get("lost", 0),
                    "gd": entry.get("goalDifference", 0),
                    "points": entry.get("points", 0),
                    "competition": comp_name,
                    "competition_id": competition,
                })
        return standings_list

    # ------------------------------------------------------------------
    # Top Scorers
    # ------------------------------------------------------------------

    def fetch_scorers(
        self, competition: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Fetch top scorers for a competition code.

        Returns normalised scorer dicts.  Empty list on error.
        """
        try:
            resp = self._client.get(
                f"{self.base_url}/competitions/{competition}/scorers",
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("fetch_scorers(%s) failed: %s", competition, exc)
            return []

        comp_name = COMPETITIONS.get(competition, competition)
        return [self._normalise_scorer(s, comp_name, competition) for s in data.get("scorers", [])]

    def _normalise_scorer(self, s: dict, comp_name: str, comp_id: str) -> dict[str, Any]:
        player = s.get("player", {})
        team = s.get("team", {})
        return {
            "id": f"scorer-{player.get('id', 'unknown')}",
            "name": player.get("name", "Unknown"),
            "team": team.get("name", "Unknown"),
            "goals": s.get("goals", 0),
            "penalties": s.get("penalties") or 0,
            "assists": s.get("assists") or 0,
            "played_matches": s.get("playedMatches", 0),
            "competition": comp_name,
            "competition_id": comp_id,
        }
