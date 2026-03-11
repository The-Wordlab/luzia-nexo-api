"""Sports feed crawler and ChromaDB ingestion module.

Handles:
- RSS feed crawling (BBC Sport, ESPN FC, Sky Sports)
- Structured match results from football-data.org or seed data
- League standings ingestion
- ChromaDB upsert for three collections: articles, match_results, standings

Environment variables:
    SPORT_FEEDS               Comma-separated RSS feed URLs (default: BBC + ESPN)
    FOOTBALL_DATA_API_KEY     API key for football-data.org (leave empty for seed data)
    FOOTBALL_DATA_COMPETITION Comma-separated competition IDs, e.g. "PL,BL1,PD"
    EMBEDDING_MODEL           litellm embedding model string (default: vertex_ai/text-embedding-004)
    CHROMA_PERSIST_DIR        Path to ChromaDB persistence directory
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import textwrap
from datetime import datetime
from typing import Any

import chromadb
import feedparser
import httpx
import litellm
from bs4 import BeautifulSoup

try:
    import psycopg
except ImportError:  # pragma: no cover - optional for local chroma mode
    psycopg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR: str = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")


def _configure_vertex_env_defaults() -> None:
    """Map common GCP env vars into LiteLLM Vertex vars when unset."""
    project = (
        os.environ.get("VERTEXAI_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
    )
    location = (
        os.environ.get("VERTEXAI_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GCP_REGION")
    )
    if project:
        os.environ.setdefault("VERTEXAI_PROJECT", project)
    if location:
        os.environ.setdefault("VERTEXAI_LOCATION", location)


_configure_vertex_env_defaults()

EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "vertex_ai/text-embedding-004")
FOOTBALL_DATA_API_KEY: str = os.environ.get("FOOTBALL_DATA_API_KEY", "")
VECTOR_STORE_BACKEND: str = os.environ.get("VECTOR_STORE_BACKEND", "chroma").strip().lower()
PGVECTOR_DSN: str = os.environ.get("PGVECTOR_DSN", "")
PGVECTOR_SCHEMA: str = os.environ.get("PGVECTOR_SCHEMA", "rag_sports")
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

_raw_competition_ids = os.environ.get("FOOTBALL_DATA_COMPETITION", "PL")
COMPETITION_IDS: list[str] = [c.strip() for c in _raw_competition_ids.split(",") if c.strip()]

DEFAULT_SPORT_FEEDS = [
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.espn.com/espn/rss/soccer/news",
    "https://www.skysports.com/rss/12040",  # Sky Sports Football
]
_raw_feeds = os.environ.get("SPORT_FEEDS", "")
SPORT_FEEDS: list[str] = [f.strip() for f in _raw_feeds.split(",") if f.strip()] or DEFAULT_SPORT_FEEDS

COLLECTION_ARTICLES = "articles"
COLLECTION_MATCHES = "match_results"
COLLECTION_STANDINGS = "standings"

CHUNK_SIZE_CHARS = 1200   # ~300 tokens at 4 chars/token
CHUNK_OVERLAP_CHARS = 150
EMBEDDING_MAX_BATCH = 250

# ---------------------------------------------------------------------------
# Seed data (used when live API is unavailable)
# ---------------------------------------------------------------------------

SEED_MATCHES: list[dict[str, Any]] = [
    {
        "id": "match-001",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_score": 3,
        "away_score": 1,
        "competition": "Premier League",
        "competition_id": "PL",
        "matchday": 28,
        "date": "March 5, 2026",
        "venue": "Emirates Stadium",
        "goals": "Saka 12', Havertz 45', Rice 67' - Palmer 55'",
        "status": "FINISHED",
    },
    {
        "id": "match-002",
        "home_team": "Manchester City",
        "away_team": "Liverpool",
        "home_score": 2,
        "away_score": 2,
        "competition": "Premier League",
        "competition_id": "PL",
        "matchday": 28,
        "date": "March 5, 2026",
        "venue": "Etihad Stadium",
        "goals": "Haaland 23', De Bruyne 78' - Salah 34', Nunez 90'",
        "status": "FINISHED",
    },
    {
        "id": "match-003",
        "home_team": "Tottenham",
        "away_team": "Manchester United",
        "home_score": 4,
        "away_score": 0,
        "competition": "Premier League",
        "competition_id": "PL",
        "matchday": 28,
        "date": "March 5, 2026",
        "venue": "Tottenham Hotspur Stadium",
        "goals": "Son 8', 45', Maddison 62', Richarlison 88'",
        "status": "FINISHED",
    },
    {
        "id": "match-004",
        "home_team": "Newcastle United",
        "away_team": "Aston Villa",
        "home_score": 1,
        "away_score": 0,
        "competition": "Premier League",
        "competition_id": "PL",
        "matchday": 28,
        "date": "March 4, 2026",
        "venue": "St. James' Park",
        "goals": "Isak 71'",
        "status": "FINISHED",
    },
    {
        "id": "match-005",
        "home_team": "Brighton",
        "away_team": "Everton",
        "home_score": 2,
        "away_score": 1,
        "competition": "Premier League",
        "competition_id": "PL",
        "matchday": 28,
        "date": "March 4, 2026",
        "venue": "Amex Stadium",
        "goals": "Welbeck 15', Mitoma 55' - Calvert-Lewin 80'",
        "status": "FINISHED",
    },
    {
        "id": "match-006",
        "home_team": "Real Madrid",
        "away_team": "Barcelona",
        "home_score": 2,
        "away_score": 3,
        "competition": "La Liga",
        "competition_id": "PD",
        "matchday": 26,
        "date": "March 2, 2026",
        "venue": "Santiago Bernabeu",
        "goals": "Vinicius 22', Bellingham 67' - Lewandowski 10', 45', Yamal 90'",
        "status": "FINISHED",
    },
    {
        "id": "match-007",
        "home_team": "Bayern Munich",
        "away_team": "Borussia Dortmund",
        "home_score": 3,
        "away_score": 1,
        "competition": "Bundesliga",
        "competition_id": "BL1",
        "matchday": 25,
        "date": "March 1, 2026",
        "venue": "Allianz Arena",
        "goals": "Kane 5', 44', Musiala 78' - Adeyemi 60'",
        "status": "FINISHED",
    },
    {
        "id": "match-008",
        "home_team": "PSG",
        "away_team": "Marseille",
        "home_score": 3,
        "away_score": 0,
        "competition": "Ligue 1",
        "competition_id": "FL1",
        "matchday": 24,
        "date": "February 28, 2026",
        "venue": "Parc des Princes",
        "goals": "Mbappe 12', 34', Dembele 56'",
        "status": "FINISHED",
    },
    {
        "id": "match-009",
        "home_team": "Inter Milan",
        "away_team": "AC Milan",
        "home_score": 2,
        "away_score": 1,
        "competition": "Serie A",
        "competition_id": "SA",
        "matchday": 27,
        "date": "February 26, 2026",
        "venue": "San Siro",
        "goals": "Lautaro 33', Thuram 70' - Leao 55'",
        "status": "FINISHED",
    },
    {
        "id": "match-010",
        "home_team": "Chelsea",
        "away_team": "Arsenal",
        "home_score": 1,
        "away_score": 2,
        "competition": "FA Cup",
        "competition_id": "FAC",
        "matchday": "Quarter-Final",
        "date": "February 22, 2026",
        "venue": "Stamford Bridge",
        "goals": "Enzo 45' - Martinelli 30', Trossard 88'",
        "status": "FINISHED",
    },
]

SEED_STANDINGS: list[dict[str, Any]] = [
    {"position": 1, "team": "Arsenal", "played": 28, "won": 20, "drawn": 5, "lost": 3, "gd": 42, "points": 65, "competition": "Premier League"},
    {"position": 2, "team": "Liverpool", "played": 28, "won": 19, "drawn": 6, "lost": 3, "gd": 38, "points": 63, "competition": "Premier League"},
    {"position": 3, "team": "Manchester City", "played": 28, "won": 17, "drawn": 7, "lost": 4, "gd": 29, "points": 58, "competition": "Premier League"},
    {"position": 4, "team": "Chelsea", "played": 28, "won": 16, "drawn": 5, "lost": 7, "gd": 18, "points": 53, "competition": "Premier League"},
    {"position": 5, "team": "Tottenham", "played": 28, "won": 15, "drawn": 6, "lost": 7, "gd": 15, "points": 51, "competition": "Premier League"},
    {"position": 6, "team": "Aston Villa", "played": 28, "won": 14, "drawn": 7, "lost": 7, "gd": 10, "points": 49, "competition": "Premier League"},
    {"position": 7, "team": "Newcastle United", "played": 28, "won": 13, "drawn": 8, "lost": 7, "gd": 8, "points": 47, "competition": "Premier League"},
    {"position": 8, "team": "Brighton", "played": 28, "won": 13, "drawn": 5, "lost": 10, "gd": 5, "points": 44, "competition": "Premier League"},
    {"position": 9, "team": "Manchester United", "played": 28, "won": 10, "drawn": 7, "lost": 11, "gd": -8, "points": 37, "competition": "Premier League"},
    {"position": 10, "team": "West Ham", "played": 28, "won": 9, "drawn": 8, "lost": 11, "gd": -10, "points": 35, "competition": "Premier League"},
]

# ---------------------------------------------------------------------------
# Vector-store helpers (Chroma or pgvector)
# ---------------------------------------------------------------------------

_chroma_client: chromadb.ClientAPI | None = None
_pg_conn: psycopg.Connection | None = None
_pg_collections: dict[str, "_PgVectorCollection"] = {}


def _sanitize_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", value).lower()


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def _pg_connection() -> psycopg.Connection:
    global _pg_conn
    if psycopg is None:
        raise RuntimeError("psycopg is required when VECTOR_STORE_BACKEND=pgvector")
    if _pg_conn is None:
        if not PGVECTOR_DSN:
            raise RuntimeError("PGVECTOR_DSN is required when VECTOR_STORE_BACKEND=pgvector")
        _pg_conn = psycopg.connect(PGVECTOR_DSN, autocommit=True)
    return _pg_conn


class _PgVectorCollection:
    def __init__(self, name: str) -> None:
        self.schema = _sanitize_identifier(PGVECTOR_SCHEMA)
        self.table = _sanitize_identifier(name)
        self._dim: int | None = None

    def _table_ref(self) -> str:
        return f'"{self.schema}"."{self.table}"'

    def _exists(self, conn: psycopg.Connection) -> bool:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"{self.schema}.{self.table}",))
            return cur.fetchone()[0] is not None

    def _ensure_table(self, dim: int) -> None:
        conn = _pg_connection()
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_ref()} (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    embedding VECTOR({dim}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        self._dim = dim

    def _drop_table(self) -> None:
        conn = _pg_connection()
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self._table_ref()}")

    @staticmethod
    def _is_dimension_mismatch(exc: Exception) -> bool:
        message = str(exc).lower()
        return "different vector dimensions" in message or (
            "expected" in message and "dimensions" in message
        )

    def count(self) -> int:
        conn = _pg_connection()
        if not self._exists(conn):
            return 0
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {self._table_ref()}")
            return int(cur.fetchone()[0])

    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not embeddings:
            return
        dim = len(embeddings[0])
        if self._dim is None or self._dim != dim:
            self._ensure_table(dim)
        conn = _pg_connection()
        rows = [
            (ids[i], documents[i], _vector_literal(embeddings[i]), json.dumps(metadatas[i] or {}))
            for i in range(len(ids))
        ]
        with conn.cursor() as cur:
            try:
                cur.executemany(
                    f"""
                    INSERT INTO {self._table_ref()} (id, document, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    rows,
                )
            except Exception as exc:
                if not self._is_dimension_mismatch(exc):
                    raise
                logger.warning(
                    "Detected pgvector dimension mismatch for %s. Recreating table with dim=%s.",
                    self._table_ref(),
                    dim,
                )
                self._drop_table()
                self._ensure_table(dim)
                cur.executemany(
                    f"""
                    INSERT INTO {self._table_ref()} (id, document, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    rows,
                )

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        include: list[str] | None = None,
    ) -> dict[str, list[list[Any]]]:
        include = include or ["documents", "metadatas", "distances"]
        if not query_embeddings:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        conn = _pg_connection()
        if not self._exists(conn):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        qvec = _vector_literal(query_embeddings[0])
        with conn.cursor() as cur:
            try:
                cur.execute(
                    f"""
                    SELECT id, document, metadata, (embedding <=> %s::vector) AS distance
                    FROM {self._table_ref()}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qvec, qvec, n_results),
                )
            except Exception as exc:
                if not self._is_dimension_mismatch(exc):
                    raise
                dim = len(query_embeddings[0])
                logger.warning(
                    "Detected pgvector dimension mismatch for %s query. Recreating table with dim=%s.",
                    self._table_ref(),
                    dim,
                )
                self._drop_table()
                self._ensure_table(dim)
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
            rows = cur.fetchall()
        ids = [r[0] for r in rows]
        docs = [r[1] for r in rows]
        metas = [r[2] for r in rows]
        dists = [float(r[3]) for r in rows]
        result: dict[str, list[list[Any]]] = {"ids": [ids]}
        if "documents" in include:
            result["documents"] = [docs]
        if "metadatas" in include:
            result["metadatas"] = [metas]
        if "distances" in include:
            result["distances"] = [dists]
        return result


def get_chroma_client(persist_dir: str = CHROMA_PERSIST_DIR) -> chromadb.ClientAPI:
    """Return (or create) a persistent ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def get_collection(name: str) -> Any:
    """Get or create a vector collection by name."""
    if VECTOR_STORE_BACKEND == "pgvector":
        if name not in _pg_collections:
            _pg_collections[name] = _PgVectorCollection(name)
        return _pg_collections[name]

    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_client() -> None:
    """Reset global vector clients (used in tests)."""
    global _chroma_client, _pg_conn
    _chroma_client = None
    _pg_conn = None
    _pg_collections.clear()


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, falling back to zero vectors on failure."""
    if not texts:
        return []
    fallback_dim = int(os.environ.get("EMBEDDING_FALLBACK_DIM", "768"))
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBEDDING_MAX_BATCH):
        batch = texts[start:start + EMBEDDING_MAX_BATCH]
        try:
            response = litellm.embedding(model=EMBEDDING_MODEL, input=batch)
            embeddings.extend([item["embedding"] for item in response["data"]])
        except Exception as exc:
            logger.warning("Embedding failed (%s); using zero vectors", exc)
            embeddings.extend([[0.0] * fallback_dim for _ in batch])
    return embeddings


def safe_id(text: str) -> str:
    """Produce a stable, ChromaDB-safe document ID from arbitrary text."""
    return hashlib.md5(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def strip_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    step = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    while start < len(text):
        end = start + CHUNK_SIZE_CHARS
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks


# ---------------------------------------------------------------------------
# Match data formatting
# ---------------------------------------------------------------------------


def format_match_text(match: dict[str, Any]) -> str:
    """Render a match dict as a searchable text string."""
    return (
        f"{match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']} | "
        f"{match['competition']} | Matchday {match['matchday']} | {match['date']} | "
        f"Venue: {match.get('venue', 'N/A')} | Goals: {match.get('goals', 'N/A')}"
    )


def format_standings_text(standings: list[dict[str, Any]], competition: str) -> str:
    """Render standings as a searchable text block."""
    lines = [f"{s['position']}. {s['team']}: P{s['played']} W{s['won']} D{s['drawn']} "
             f"L{s['lost']} GD{s['gd']:+d} Pts{s['points']}"
             for s in standings]
    return f"{competition} Standings:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# RSS feed crawler
# ---------------------------------------------------------------------------


async def crawl_feeds(feeds: list[str] | None = None) -> int:
    """Crawl RSS feeds and upsert articles into ChromaDB.

    Returns the total number of article chunks indexed.
    """
    feeds = feeds or SPORT_FEEDS
    collection = get_collection(COLLECTION_ARTICLES)
    total = 0

    for feed_url in feeds:
        logger.info("Crawling feed: %s", feed_url)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", feed_url, exc)
            continue

        feed_title = parsed.feed.get("title", feed_url)
        entries = parsed.get("entries", [])[:25]

        for entry in entries:
            entry_id = entry.get("id") or entry.get("link", "")
            if not entry_id:
                continue

            title: str = entry.get("title", "")
            link: str = entry.get("link", "")
            published: str = entry.get("published", "")
            summary_html: str = entry.get("summary", "") or entry.get("description", "")
            summary = strip_html(summary_html)

            # Use summary as body; optionally enrich with full article text
            full_text = f"{title}. {summary}".strip()
            if not full_text or full_text == ".":
                continue

            chunks = chunk_text(full_text)
            if not chunks:
                continue

            # Embed in batches of 32
            batch_size = 32
            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start: batch_start + batch_size]
                embeddings = embed_texts(batch)

                ids = [safe_id(f"{entry_id}:{batch_start + i}") for i in range(len(batch))]
                metadatas = [
                    {
                        "title": title[:200],
                        "link": link[:500],
                        "feed": feed_title[:200],
                        "published": published[:100],
                        "type": "article",
                        "excerpt": textwrap.shorten(chunk, width=200, placeholder="..."),
                    }
                    for chunk in batch
                ]
                collection.upsert(ids=ids, embeddings=embeddings, documents=batch, metadatas=metadatas)
                total += len(batch)

    logger.info("Feed crawl complete. %d chunks indexed.", total)
    return total


# ---------------------------------------------------------------------------
# Live match results from football-data.org
# ---------------------------------------------------------------------------


async def fetch_live_matches(competition_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Fetch recent/live match results from football-data.org.

    Returns a list of match dicts in the same format as SEED_MATCHES.
    Falls back to an empty list when FOOTBALL_DATA_API_KEY is unset.
    """
    if not FOOTBALL_DATA_API_KEY:
        logger.info("FOOTBALL_DATA_API_KEY not set; skipping live match fetch")
        return []

    competition_ids = competition_ids or COMPETITION_IDS
    matches: list[dict[str, Any]] = []
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for comp_id in competition_ids:
            url = f"{FOOTBALL_DATA_BASE_URL}/competitions/{comp_id}/matches"
            params = {"status": "FINISHED", "limit": 10}
            try:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("Failed to fetch matches for %s: %s", comp_id, exc)
                continue

            for raw in data.get("matches", []):
                home = raw.get("homeTeam", {}).get("shortName") or raw.get("homeTeam", {}).get("name", "")
                away = raw.get("awayTeam", {}).get("shortName") or raw.get("awayTeam", {}).get("name", "")
                score = raw.get("score", {})
                full_time = score.get("fullTime", {})
                home_score = full_time.get("home")
                away_score = full_time.get("away")

                if home_score is None or away_score is None:
                    continue

                match_date = raw.get("utcDate", "")[:10]  # YYYY-MM-DD
                competition_name = raw.get("competition", {}).get("name", comp_id)
                matchday = raw.get("matchday", "N/A")
                venue = raw.get("venue", "N/A") or "N/A"
                match_id = str(raw.get("id", safe_id(f"{home}{away}{match_date}")))

                matches.append(
                    {
                        "id": f"live-{match_id}",
                        "home_team": home,
                        "away_team": away,
                        "home_score": home_score,
                        "away_score": away_score,
                        "competition": competition_name,
                        "competition_id": comp_id,
                        "matchday": matchday,
                        "date": match_date,
                        "venue": venue,
                        "goals": "",  # football-data.org goal scorers are in a separate endpoint
                        "status": raw.get("status", "FINISHED"),
                    }
                )

    logger.info("Fetched %d live matches from football-data.org", len(matches))
    return matches


async def fetch_standings(competition_id: str) -> list[dict[str, Any]]:
    """Fetch league standings from football-data.org.

    Returns an empty list when FOOTBALL_DATA_API_KEY is unset.
    """
    if not FOOTBALL_DATA_API_KEY:
        return []

    url = f"{FOOTBALL_DATA_BASE_URL}/competitions/{competition_id}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch standings for %s: %s", competition_id, exc)
        return []

    competition_name = data.get("competition", {}).get("name", competition_id)
    standings: list[dict[str, Any]] = []

    for group in data.get("standings", []):
        if group.get("type") != "TOTAL":
            continue
        for row in group.get("table", []):
            standings.append(
                {
                    "position": row.get("position", 0),
                    "team": row.get("team", {}).get("shortName") or row.get("team", {}).get("name", ""),
                    "played": row.get("playedGames", 0),
                    "won": row.get("won", 0),
                    "drawn": row.get("draw", 0),
                    "lost": row.get("lost", 0),
                    "gd": row.get("goalDifference", 0),
                    "points": row.get("points", 0),
                    "competition": competition_name,
                }
            )

    return standings


# ---------------------------------------------------------------------------
# ChromaDB ingestion for matches
# ---------------------------------------------------------------------------


def ingest_matches(matches: list[dict[str, Any]]) -> int:
    """Upsert match records into the match_results ChromaDB collection.

    Returns the number of records upserted.
    """
    if not matches:
        return 0

    collection = get_collection(COLLECTION_MATCHES)
    texts = [format_match_text(m) for m in matches]
    embeddings = embed_texts(texts)
    ids = [m["id"] for m in matches]
    metadatas = [
        {
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "competition": m["competition"],
            "competition_id": m.get("competition_id", ""),
            "date": str(m["date"]),
            "venue": m.get("venue", ""),
            "goals": m.get("goals", ""),
            "home_score": int(m["home_score"]),
            "away_score": int(m["away_score"]),
            "matchday": str(m["matchday"]),
            "status": m.get("status", "FINISHED"),
        }
        for m in matches
    ]
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("Upserted %d match records into ChromaDB", len(matches))
    return len(matches)


def ingest_standings(standings: list[dict[str, Any]], competition: str) -> int:
    """Upsert standings as a single document in the standings collection.

    Returns 1 if upserted, 0 otherwise.
    """
    if not standings:
        return 0

    collection = get_collection(COLLECTION_STANDINGS)
    text = format_standings_text(standings, competition)
    doc_id = safe_id(f"standings-{competition}-{datetime.utcnow().strftime('%Y%m%d')}")
    embeddings = embed_texts([text])
    collection.upsert(
        ids=[doc_id],
        embeddings=embeddings,
        documents=[text],
        metadatas=[
            {
                "type": "standings",
                "competition": competition,
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "top_team": standings[0]["team"] if standings else "",
            }
        ],
    )
    logger.info("Upserted standings for %s", competition)
    return 1


# ---------------------------------------------------------------------------
# Seed helpers (used at startup so demo works without live API)
# ---------------------------------------------------------------------------


def seed_matches() -> None:
    """Seed the match_results collection with hardcoded data if empty."""
    collection = get_collection(COLLECTION_MATCHES)
    if collection.count() >= len(SEED_MATCHES):
        logger.info("match_results collection already populated (%d), skipping seed", collection.count())
        return
    ingest_matches(SEED_MATCHES)


def seed_standings() -> None:
    """Seed the standings collection with Premier League data if empty."""
    collection = get_collection(COLLECTION_STANDINGS)
    if collection.count() > 0:
        logger.info("standings collection already populated, skipping seed")
        return
    ingest_standings(SEED_STANDINGS, "Premier League")


# ---------------------------------------------------------------------------
# High-level ingest routines (called from server endpoints)
# ---------------------------------------------------------------------------


async def run_full_ingest(
    feeds: list[str] | None = None,
    competition_ids: list[str] | None = None,
) -> dict[str, int]:
    """Crawl RSS feeds + fetch live match results + standings. Returns summary counts."""
    competition_ids = competition_ids or COMPETITION_IDS

    # Articles
    article_chunks = await crawl_feeds(feeds)

    # Live matches (falls back to seed on missing API key)
    live_matches = await fetch_live_matches(competition_ids)
    if live_matches:
        match_count = ingest_matches(live_matches)
    else:
        seed_matches()
        match_count = get_collection(COLLECTION_MATCHES).count()

    # Standings
    standings_count = 0
    for comp_id in competition_ids:
        standings = await fetch_standings(comp_id)
        if standings:
            competition_name = standings[0].get("competition", comp_id) if standings else comp_id
            standings_count += ingest_standings(standings, competition_name)

    if standings_count == 0:
        seed_standings()
        standings_count = get_collection(COLLECTION_STANDINGS).count()

    return {
        "article_chunks": article_chunks,
        "match_records": match_count,
        "standings_docs": standings_count,
    }


async def run_live_ingest(competition_ids: list[str] | None = None) -> dict[str, int]:
    """Lightweight ingest: only fetch live match results and standings (no RSS crawl)."""
    competition_ids = competition_ids or COMPETITION_IDS

    live_matches = await fetch_live_matches(competition_ids)
    match_count = ingest_matches(live_matches) if live_matches else 0

    standings_count = 0
    for comp_id in competition_ids:
        standings = await fetch_standings(comp_id)
        if standings:
            competition_name = standings[0].get("competition", comp_id) if standings else comp_id
            standings_count += ingest_standings(standings, competition_name)

    return {
        "match_records_updated": match_count,
        "standings_docs_updated": standings_count,
    }
