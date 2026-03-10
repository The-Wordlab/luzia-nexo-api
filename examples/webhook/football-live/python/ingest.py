"""ChromaDB ingest pipeline for football-live webhook.

Manages three collections: matches, standings, scorers.
Includes seed data for demo mode (no API key required).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import chromadb
import litellm

from football_api import COMPETITIONS, FootballDataClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ChromaDB setup
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_football_live")
EMBEDDING_MODEL = "text-embedding-3-small"

COLLECTION_MATCHES = "matches"
COLLECTION_STANDINGS = "standings"
COLLECTION_SCORERS = "scorers"

_chroma_client: chromadb.ClientAPI | None = None


def get_chroma_client(persist_dir: str = CHROMA_PERSIST_DIR) -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def get_collection(name: str) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts via litellm, falling back to zero vectors."""
    try:
        response = litellm.embedding(model=EMBEDDING_MODEL, input=texts)
        return [item["embedding"] for item in response["data"]]
    except Exception as exc:
        logger.warning("Embedding failed (%s); using zero vectors", exc)
        return [[0.0] * 1536 for _ in texts]


def safe_id(raw: str) -> str:
    """Sanitise a string for use as a ChromaDB document ID."""
    return raw.replace(" ", "-").replace("/", "-").lower()[:128]


# ---------------------------------------------------------------------------
# Text formatters
# ---------------------------------------------------------------------------


def format_match_text(m: dict[str, Any]) -> str:
    """Human-readable match text for embedding."""
    live_tag = ""
    if m.get("status") == "IN_PLAY" and m.get("live_minute"):
        live_tag = f" [LIVE {m['live_minute']}']"
    elif m.get("status") == "IN_PLAY":
        live_tag = " [LIVE]"

    score = f"{m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}"
    parts = [
        f"{score}{live_tag}",
        f"{m.get('competition', '')} Matchday {m.get('matchday', '')}",
        f"Date: {m.get('date', '')}",
    ]
    if m.get("goals"):
        parts.append(f"Goals: {m['goals']}")
    if m.get("venue"):
        parts.append(f"Venue: {m['venue']}")
    return " | ".join(parts)


def format_standings_text(standings: list[dict[str, Any]], competition: str) -> str:
    """One document per competition with all positions."""
    lines = [f"{competition} Standings"]
    for s in standings:
        lines.append(
            f"{s['position']}. {s['team']} - W{s['won']} D{s['drawn']} L{s['lost']} "
            f"GD{s['gd']:+d} · {s['points']} pts"
        )
    return "\n".join(lines)


def format_scorer_text(s: dict[str, Any]) -> str:
    """Human-readable scorer text for embedding."""
    pen = f" ({s['penalties']} pen)" if s.get("penalties") else ""
    assists = f" · {s['assists']} assists" if s.get("assists") else ""
    return (
        f"{s.get('name', 'Unknown')} ({s.get('team', 'Unknown')}): "
        f"{s.get('goals', 0)} goals{pen}{assists} — {s.get('competition', '')}"
    )


# ---------------------------------------------------------------------------
# Ingest functions
# ---------------------------------------------------------------------------


def ingest_matches(matches: list[dict[str, Any]]) -> int:
    if not matches:
        return 0
    collection = get_collection(COLLECTION_MATCHES)
    texts = [format_match_text(m) for m in matches]
    embeddings = embed_texts(texts)
    ids = [safe_id(m["id"]) for m in matches]
    metadatas = [
        {
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "home_score": m["home_score"],
            "away_score": m["away_score"],
            "competition": m.get("competition", ""),
            "competition_id": m.get("competition_id", ""),
            "matchday": m.get("matchday", 0),
            "date": m.get("date", ""),
            "status": m.get("status", "FINISHED"),
            "goals": m.get("goals", ""),
            "venue": m.get("venue", ""),
            "live_minute": m.get("live_minute") or 0,
        }
        for m in matches
    ]
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("Upserted %d matches into ChromaDB", len(matches))
    return len(matches)


def ingest_standings(standings: list[dict[str, Any]], competition: str) -> int:
    if not standings:
        return 0
    collection = get_collection(COLLECTION_STANDINGS)
    text = format_standings_text(standings, competition)
    embeddings = embed_texts([text])
    doc_id = safe_id(f"standings-{competition}")
    metadatas = [{"competition": competition, "count": len(standings)}]
    # Also upsert individual entries for per-team search
    all_texts = [text]
    all_ids = [doc_id]
    all_metadatas = metadatas
    all_embeddings = embeddings

    for s in standings:
        entry_text = (
            f"{s['position']}. {s['team']} — W{s['won']} D{s['drawn']} L{s['lost']} "
            f"GD{s['gd']:+d} · {s['points']} pts — {competition}"
        )
        entry_id = safe_id(f"standing-{competition}-{s['position']}")
        all_texts.append(entry_text)
        all_ids.append(entry_id)
        all_metadatas.append({
            "position": s["position"],
            "team": s["team"],
            "played": s.get("played", 0),
            "won": s["won"],
            "drawn": s["drawn"],
            "lost": s["lost"],
            "gd": s["gd"],
            "points": s["points"],
            "competition": competition,
            "competition_id": s.get("competition_id", ""),
        })

    extra_embeddings = embed_texts(all_texts[1:])
    all_embeddings.extend(extra_embeddings)
    collection.upsert(ids=all_ids, embeddings=all_embeddings, documents=all_texts, metadatas=all_metadatas)
    logger.info("Upserted standings for %s (%d entries) into ChromaDB", competition, len(standings))
    return len(standings)


def ingest_scorers(scorers: list[dict[str, Any]]) -> int:
    if not scorers:
        return 0
    collection = get_collection(COLLECTION_SCORERS)
    texts = [format_scorer_text(s) for s in scorers]
    embeddings = embed_texts(texts)
    ids = [safe_id(s["id"]) for s in scorers]
    metadatas = [
        {
            "name": s["name"],
            "team": s["team"],
            "goals": s["goals"],
            "penalties": s.get("penalties", 0),
            "assists": s.get("assists", 0),
            "played_matches": s.get("played_matches", 0),
            "competition": s.get("competition", ""),
            "competition_id": s.get("competition_id", ""),
        }
        for s in scorers
    ]
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("Upserted %d scorers into ChromaDB", len(scorers))
    return len(scorers)


# ---------------------------------------------------------------------------
# Seed data — works without API key
# ---------------------------------------------------------------------------

SEED_MATCHES: list[dict[str, Any]] = [
    # Premier League
    {"id": "match-001", "home_team": "Arsenal", "away_team": "Chelsea", "home_score": 3, "away_score": 1, "competition": "Premier League", "competition_id": "PL", "matchday": 28, "date": "March 5, 2026", "venue": "Emirates Stadium", "goals": "Saka 12', Havertz 45', Rice 67' - Palmer 55'", "status": "FINISHED"},
    {"id": "match-002", "home_team": "Liverpool", "away_team": "Man City", "home_score": 2, "away_score": 2, "competition": "Premier League", "competition_id": "PL", "matchday": 28, "date": "March 5, 2026", "venue": "Anfield", "goals": "Salah 23', Diaz 78' - Haaland 15', De Bruyne 60'", "status": "FINISHED"},
    {"id": "match-003", "home_team": "Man United", "away_team": "Tottenham", "home_score": 1, "away_score": 0, "competition": "Premier League", "competition_id": "PL", "matchday": 28, "date": "March 6, 2026", "venue": "Old Trafford", "goals": "Rashford 88'", "status": "FINISHED"},
    {"id": "match-004", "home_team": "Newcastle", "away_team": "Aston Villa", "home_score": 2, "away_score": 1, "competition": "Premier League", "competition_id": "PL", "matchday": 29, "date": "March 8, 2026", "venue": "St James' Park", "goals": "Isak 30', Gordon 55' - Watkins 72'", "status": "IN_PLAY", "live_minute": 78},
    {"id": "match-005", "home_team": "Brighton", "away_team": "West Ham", "home_score": 0, "away_score": 0, "competition": "Premier League", "competition_id": "PL", "matchday": 29, "date": "March 8, 2026", "venue": "Amex Stadium", "goals": "", "status": "SCHEDULED"},
    # La Liga
    {"id": "match-006", "home_team": "Real Madrid", "away_team": "Barcelona", "home_score": 2, "away_score": 3, "competition": "La Liga", "competition_id": "PD", "matchday": 27, "date": "March 4, 2026", "venue": "Santiago Bernabéu", "goals": "Bellingham 10', Vinícius Jr 65' - Yamal 22', Lewandowski 50', Pedri 80'", "status": "FINISHED"},
    {"id": "match-007", "home_team": "Atlético Madrid", "away_team": "Sevilla", "home_score": 1, "away_score": 0, "competition": "La Liga", "competition_id": "PD", "matchday": 27, "date": "March 4, 2026", "venue": "Metropolitano", "goals": "Griezmann 34'", "status": "FINISHED"},
    {"id": "match-008", "home_team": "Athletic Bilbao", "away_team": "Real Sociedad", "home_score": 2, "away_score": 1, "competition": "La Liga", "competition_id": "PD", "matchday": 28, "date": "March 7, 2026", "venue": "San Mamés", "goals": "Williams 15', Sancet 60' - Oyarzabal 45'", "status": "FINISHED"},
    {"id": "match-009", "home_team": "Villarreal", "away_team": "Valencia", "home_score": 0, "away_score": 0, "competition": "La Liga", "competition_id": "PD", "matchday": 28, "date": "March 8, 2026", "venue": "Estadio de la Cerámica", "goals": "", "status": "SCHEDULED"},
    {"id": "match-010", "home_team": "Girona", "away_team": "Betis", "home_score": 1, "away_score": 1, "competition": "La Liga", "competition_id": "PD", "matchday": 27, "date": "March 5, 2026", "venue": "Montilivi", "goals": "Dovbyk 38' - Isco 71'", "status": "FINISHED"},
    # Brasileirão
    {"id": "match-011", "home_team": "Flamengo", "away_team": "Palmeiras", "home_score": 2, "away_score": 1, "competition": "Brasileirão", "competition_id": "BSA", "matchday": 1, "date": "March 2, 2026", "venue": "Maracanã", "goals": "Pedro 25', Gerson 70' - Endrick 55'", "status": "FINISHED"},
    {"id": "match-012", "home_team": "Corinthians", "away_team": "São Paulo", "home_score": 1, "away_score": 1, "competition": "Brasileirão", "competition_id": "BSA", "matchday": 1, "date": "March 2, 2026", "venue": "Neo Química Arena", "goals": "Yuri Alberto 40' - Calleri 62'", "status": "FINISHED"},
    {"id": "match-013", "home_team": "Botafogo", "away_team": "Fluminense", "home_score": 3, "away_score": 0, "competition": "Brasileirão", "competition_id": "BSA", "matchday": 1, "date": "March 3, 2026", "venue": "Nilton Santos", "goals": "Luiz Henrique 12', Savarino 48', Igor Jesus 75'", "status": "FINISHED"},
    {"id": "match-014", "home_team": "Atlético-MG", "away_team": "Cruzeiro", "home_score": 0, "away_score": 0, "competition": "Brasileirão", "competition_id": "BSA", "matchday": 2, "date": "March 8, 2026", "venue": "Arena MRV", "goals": "", "status": "SCHEDULED"},
    {"id": "match-015", "home_team": "Internacional", "away_team": "Grêmio", "home_score": 1, "away_score": 0, "competition": "Brasileirão", "competition_id": "BSA", "matchday": 2, "date": "March 8, 2026", "venue": "Beira-Rio", "goals": "Alan Patrick 52'", "status": "IN_PLAY", "live_minute": 67},
]

SEED_STANDINGS: list[dict[str, Any]] = [
    # Premier League (10 teams)
    {"position": 1, "team": "Arsenal", "played": 28, "won": 20, "drawn": 5, "lost": 3, "gd": 42, "points": 65, "competition": "Premier League", "competition_id": "PL"},
    {"position": 2, "team": "Liverpool", "played": 28, "won": 19, "drawn": 6, "lost": 3, "gd": 38, "points": 63, "competition": "Premier League", "competition_id": "PL"},
    {"position": 3, "team": "Man City", "played": 28, "won": 18, "drawn": 5, "lost": 5, "gd": 35, "points": 59, "competition": "Premier League", "competition_id": "PL"},
    {"position": 4, "team": "Chelsea", "played": 28, "won": 15, "drawn": 7, "lost": 6, "gd": 18, "points": 52, "competition": "Premier League", "competition_id": "PL"},
    {"position": 5, "team": "Newcastle", "played": 28, "won": 14, "drawn": 8, "lost": 6, "gd": 15, "points": 50, "competition": "Premier League", "competition_id": "PL"},
    {"position": 6, "team": "Aston Villa", "played": 28, "won": 14, "drawn": 5, "lost": 9, "gd": 12, "points": 47, "competition": "Premier League", "competition_id": "PL"},
    {"position": 7, "team": "Man United", "played": 28, "won": 12, "drawn": 7, "lost": 9, "gd": 5, "points": 43, "competition": "Premier League", "competition_id": "PL"},
    {"position": 8, "team": "Tottenham", "played": 28, "won": 12, "drawn": 5, "lost": 11, "gd": 3, "points": 41, "competition": "Premier League", "competition_id": "PL"},
    {"position": 9, "team": "Brighton", "played": 28, "won": 11, "drawn": 6, "lost": 11, "gd": 0, "points": 39, "competition": "Premier League", "competition_id": "PL"},
    {"position": 10, "team": "West Ham", "played": 28, "won": 10, "drawn": 5, "lost": 13, "gd": -8, "points": 35, "competition": "Premier League", "competition_id": "PL"},
    # La Liga (10 teams)
    {"position": 1, "team": "Barcelona", "played": 27, "won": 21, "drawn": 3, "lost": 3, "gd": 45, "points": 66, "competition": "La Liga", "competition_id": "PD"},
    {"position": 2, "team": "Real Madrid", "played": 27, "won": 19, "drawn": 4, "lost": 4, "gd": 36, "points": 61, "competition": "La Liga", "competition_id": "PD"},
    {"position": 3, "team": "Atlético Madrid", "played": 27, "won": 17, "drawn": 5, "lost": 5, "gd": 25, "points": 56, "competition": "La Liga", "competition_id": "PD"},
    {"position": 4, "team": "Athletic Bilbao", "played": 27, "won": 14, "drawn": 8, "lost": 5, "gd": 18, "points": 50, "competition": "La Liga", "competition_id": "PD"},
    {"position": 5, "team": "Girona", "played": 27, "won": 13, "drawn": 6, "lost": 8, "gd": 10, "points": 45, "competition": "La Liga", "competition_id": "PD"},
    {"position": 6, "team": "Real Sociedad", "played": 27, "won": 12, "drawn": 7, "lost": 8, "gd": 8, "points": 43, "competition": "La Liga", "competition_id": "PD"},
    {"position": 7, "team": "Villarreal", "played": 27, "won": 11, "drawn": 8, "lost": 8, "gd": 5, "points": 41, "competition": "La Liga", "competition_id": "PD"},
    {"position": 8, "team": "Betis", "played": 27, "won": 11, "drawn": 6, "lost": 10, "gd": 2, "points": 39, "competition": "La Liga", "competition_id": "PD"},
    {"position": 9, "team": "Sevilla", "played": 27, "won": 10, "drawn": 6, "lost": 11, "gd": -3, "points": 36, "competition": "La Liga", "competition_id": "PD"},
    {"position": 10, "team": "Valencia", "played": 27, "won": 8, "drawn": 7, "lost": 12, "gd": -10, "points": 31, "competition": "La Liga", "competition_id": "PD"},
    # Brasileirão (10 teams)
    {"position": 1, "team": "Botafogo", "played": 1, "won": 1, "drawn": 0, "lost": 0, "gd": 3, "points": 3, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 2, "team": "Flamengo", "played": 1, "won": 1, "drawn": 0, "lost": 0, "gd": 1, "points": 3, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 3, "team": "Internacional", "played": 1, "won": 0, "drawn": 1, "lost": 0, "gd": 0, "points": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 4, "team": "Corinthians", "played": 1, "won": 0, "drawn": 1, "lost": 0, "gd": 0, "points": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 5, "team": "São Paulo", "played": 1, "won": 0, "drawn": 1, "lost": 0, "gd": 0, "points": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 6, "team": "Atlético-MG", "played": 0, "won": 0, "drawn": 0, "lost": 0, "gd": 0, "points": 0, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 7, "team": "Cruzeiro", "played": 0, "won": 0, "drawn": 0, "lost": 0, "gd": 0, "points": 0, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 8, "team": "Grêmio", "played": 1, "won": 0, "drawn": 0, "lost": 1, "gd": -1, "points": 0, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 9, "team": "Palmeiras", "played": 1, "won": 0, "drawn": 0, "lost": 1, "gd": -1, "points": 0, "competition": "Brasileirão", "competition_id": "BSA"},
    {"position": 10, "team": "Fluminense", "played": 1, "won": 0, "drawn": 0, "lost": 1, "gd": -3, "points": 0, "competition": "Brasileirão", "competition_id": "BSA"},
]

SEED_SCORERS: list[dict[str, Any]] = [
    # Premier League
    {"id": "scorer-001", "name": "Erling Haaland", "team": "Man City", "goals": 24, "penalties": 5, "assists": 3, "played_matches": 27, "competition": "Premier League", "competition_id": "PL"},
    {"id": "scorer-002", "name": "Mohamed Salah", "team": "Liverpool", "goals": 19, "penalties": 3, "assists": 12, "played_matches": 28, "competition": "Premier League", "competition_id": "PL"},
    {"id": "scorer-003", "name": "Bukayo Saka", "team": "Arsenal", "goals": 15, "penalties": 0, "assists": 10, "played_matches": 26, "competition": "Premier League", "competition_id": "PL"},
    {"id": "scorer-004", "name": "Cole Palmer", "team": "Chelsea", "goals": 14, "penalties": 4, "assists": 8, "played_matches": 28, "competition": "Premier League", "competition_id": "PL"},
    {"id": "scorer-005", "name": "Alexander Isak", "team": "Newcastle", "goals": 13, "penalties": 1, "assists": 4, "played_matches": 25, "competition": "Premier League", "competition_id": "PL"},
    # La Liga
    {"id": "scorer-006", "name": "Robert Lewandowski", "team": "Barcelona", "goals": 22, "penalties": 6, "assists": 5, "played_matches": 27, "competition": "La Liga", "competition_id": "PD"},
    {"id": "scorer-007", "name": "Vinícius Jr", "team": "Real Madrid", "goals": 16, "penalties": 0, "assists": 9, "played_matches": 25, "competition": "La Liga", "competition_id": "PD"},
    {"id": "scorer-008", "name": "Antoine Griezmann", "team": "Atlético Madrid", "goals": 14, "penalties": 2, "assists": 7, "played_matches": 26, "competition": "La Liga", "competition_id": "PD"},
    {"id": "scorer-009", "name": "Lamine Yamal", "team": "Barcelona", "goals": 11, "penalties": 0, "assists": 14, "played_matches": 27, "competition": "La Liga", "competition_id": "PD"},
    {"id": "scorer-010", "name": "Jude Bellingham", "team": "Real Madrid", "goals": 10, "penalties": 0, "assists": 6, "played_matches": 24, "competition": "La Liga", "competition_id": "PD"},
    # Brasileirão
    {"id": "scorer-011", "name": "Pedro", "team": "Flamengo", "goals": 1, "penalties": 0, "assists": 0, "played_matches": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"id": "scorer-012", "name": "Luiz Henrique", "team": "Botafogo", "goals": 1, "penalties": 0, "assists": 1, "played_matches": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"id": "scorer-013", "name": "Yuri Alberto", "team": "Corinthians", "goals": 1, "penalties": 0, "assists": 0, "played_matches": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"id": "scorer-014", "name": "Savarino", "team": "Botafogo", "goals": 1, "penalties": 0, "assists": 0, "played_matches": 1, "competition": "Brasileirão", "competition_id": "BSA"},
    {"id": "scorer-015", "name": "Gerson", "team": "Flamengo", "goals": 1, "penalties": 0, "assists": 1, "played_matches": 1, "competition": "Brasileirão", "competition_id": "BSA"},
]


def seed_matches() -> None:
    """Seed match collection with demo data if empty."""
    collection = get_collection(COLLECTION_MATCHES)
    if collection.count() >= len(SEED_MATCHES):
        logger.info("matches collection already populated (%d), skipping seed", collection.count())
        return
    ingest_matches(SEED_MATCHES)
    logger.info("Seeded %d matches", len(SEED_MATCHES))


def seed_standings() -> None:
    """Seed standings collection with demo data if empty."""
    collection = get_collection(COLLECTION_STANDINGS)
    if collection.count() > 0:
        logger.info("standings collection already populated, skipping seed")
        return
    for comp_id, comp_name in COMPETITIONS.items():
        league_standings = [s for s in SEED_STANDINGS if s["competition_id"] == comp_id]
        if league_standings:
            ingest_standings(league_standings, comp_name)
    logger.info("Seeded standings for %d leagues", len(COMPETITIONS))


def seed_scorers() -> None:
    """Seed scorers collection with demo data if empty."""
    collection = get_collection(COLLECTION_SCORERS)
    if collection.count() >= len(SEED_SCORERS):
        logger.info("scorers collection already populated (%d), skipping seed", collection.count())
        return
    ingest_scorers(SEED_SCORERS)
    logger.info("Seeded %d scorers", len(SEED_SCORERS))


# ---------------------------------------------------------------------------
# Full ingest from API (rate-limit aware)
# ---------------------------------------------------------------------------

RATE_LIMIT_DELAY = 7.0  # seconds between league batches (10 req/min free tier)


async def run_full_ingest(client: FootballDataClient) -> dict[str, int]:
    """Ingest matches, standings, and scorers for all 3 leagues.

    Makes 9 API calls total (3 leagues × 3 endpoints), with delays
    between league batches to stay within rate limits.
    """
    totals: dict[str, int] = {"matches": 0, "standings": 0, "scorers": 0}

    for i, (comp_id, comp_name) in enumerate(COMPETITIONS.items()):
        if i > 0:
            await asyncio.sleep(RATE_LIMIT_DELAY)

        matches = client.fetch_matches(comp_id)
        totals["matches"] += ingest_matches(matches)

        standings = client.fetch_standings(comp_id)
        totals["standings"] += ingest_standings(standings, comp_name)

        scorers = client.fetch_scorers(comp_id)
        totals["scorers"] += ingest_scorers(scorers)

        logger.info("Ingested %s: %d matches, %d standings, %d scorers",
                     comp_name, len(matches), len(standings), len(scorers))

    return totals


async def run_live_ingest(client: FootballDataClient) -> int:
    """Lightweight ingest: matches only (3 API calls for live polling)."""
    total = 0
    for i, comp_id in enumerate(COMPETITIONS):
        if i > 0:
            await asyncio.sleep(RATE_LIMIT_DELAY)
        matches = client.fetch_matches(comp_id, status="IN_PLAY")
        total += ingest_matches(matches)
    return total
