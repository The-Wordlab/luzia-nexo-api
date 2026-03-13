"""Travel content crawler and pgvector ingestion module.

Handles:
- RSS feed crawling (travel blogs, destination guides)
- Hardcoded destination seed profiles (10+ destinations)
- Two pgvector collections: destinations, articles
- pgvector upsert helpers

Environment variables:
    TRAVEL_FEEDS               Comma-separated RSS feed URLs (default: Lonely Planet + Nomadic Matt)
    EMBEDDING_MODEL            litellm embedding model string (default: vertex_ai/text-embedding-004)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import textwrap
from typing import Any

import feedparser
import litellm
from bs4 import BeautifulSoup

try:
    import psycopg
except ImportError:
    psycopg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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
VECTOR_STORE_BACKEND: str = os.environ.get("VECTOR_STORE_BACKEND", "pgvector").strip().lower()
PGVECTOR_DSN: str = os.environ.get("PGVECTOR_DSN", "")
PGVECTOR_SCHEMA: str = os.environ.get("PGVECTOR_SCHEMA", "rag_travel")
if VECTOR_STORE_BACKEND != "pgvector":
    raise RuntimeError(
        "travel-rag only supports VECTOR_STORE_BACKEND=pgvector. Remove any legacy vector-store override."
    )

DEFAULT_TRAVEL_FEEDS = [
    "https://www.lonelyplanet.com/news/feed",
    "https://www.nomadicmatt.com/feed/",
    "https://feeds.feedburner.com/TravelChannel",
]
_raw_feeds = os.environ.get("TRAVEL_FEEDS", "")
TRAVEL_FEEDS: list[str] = [f.strip() for f in _raw_feeds.split(",") if f.strip()] or DEFAULT_TRAVEL_FEEDS

COLLECTION_DESTINATIONS = "destinations"
COLLECTION_ARTICLES = "travel_articles"

CHUNK_SIZE_CHARS = 1500
CHUNK_OVERLAP_CHARS = 150
EMBEDDING_MAX_BATCH = 250

# ---------------------------------------------------------------------------
# Destination seed data
# ---------------------------------------------------------------------------

SEED_DESTINATIONS: list[dict[str, Any]] = [
    {
        "id": "dest-paris",
        "city": "Paris",
        "country": "France",
        "region": "Western Europe",
        "description": (
            "Paris, the City of Light, is one of the world's most iconic travel destinations. "
            "Home to the Eiffel Tower, the Louvre, Notre-Dame Cathedral, and world-class cuisine, "
            "Paris offers an unparalleled blend of art, history, fashion, and gastronomy. "
            "Stroll along the Seine, explore Montmartre's bohemian streets, or sample croissants "
            "at a sidewalk café. Paris is romantic, sophisticated, and endlessly captivating."
        ),
        "highlights": "Eiffel Tower, Louvre Museum, Notre-Dame, Musée d'Orsay, Champs-Élysées, Versailles, Montmartre",
        "best_time": "April to June, September to October",
        "budget_range": "$150–$300/day",
        "language": "French",
        "currency": "Euro (EUR)",
        "timezone": "CET (UTC+1)",
        "visa_info": "Schengen visa for non-EU visitors",
        "tags": ["romantic", "culture", "history", "art", "food", "architecture"],
    },
    {
        "id": "dest-tokyo",
        "city": "Tokyo",
        "country": "Japan",
        "region": "East Asia",
        "description": (
            "Tokyo is a mesmerising metropolis where ancient temples sit beside neon-lit skyscrapers. "
            "Japan's capital blends ultramodern technology with deep-rooted traditions — from the "
            "serene Senso-ji temple in Asakusa to the electric energy of Shibuya Crossing. "
            "Renowned for its world-class sushi, ramen, and street food, Tokyo offers an extraordinary "
            "culinary journey. Cherry blossom season transforms parks into pink paradise."
        ),
        "highlights": "Shibuya Crossing, Senso-ji Temple, Shinjuku, Tsukiji Market, teamLab, Mount Fuji day trip",
        "best_time": "March to May (cherry blossoms), October to November",
        "budget_range": "$80–$200/day",
        "language": "Japanese",
        "currency": "Japanese Yen (JPY)",
        "timezone": "JST (UTC+9)",
        "visa_info": "Visa-free for many nationalities up to 90 days",
        "tags": ["modern", "culture", "food", "technology", "temples", "nature"],
    },
    {
        "id": "dest-barcelona",
        "city": "Barcelona",
        "country": "Spain",
        "region": "Southern Europe",
        "description": (
            "Barcelona is a vibrant coastal city bursting with Gaudí's extraordinary architecture, "
            "world-class beaches, and a pulsating food and nightlife scene. Wander the Gothic Quarter's "
            "medieval streets, marvel at the Sagrada Família's surreal spires, and feast on fresh seafood "
            "along La Barceloneta beach. The city's unique Catalan identity, art scene, and warm climate "
            "make it one of Europe's most beloved destinations."
        ),
        "highlights": "Sagrada Família, Park Güell, Gothic Quarter, La Barceloneta, Camp Nou, La Boqueria",
        "best_time": "May to June, September to October",
        "budget_range": "$100–$220/day",
        "language": "Catalan, Spanish",
        "currency": "Euro (EUR)",
        "timezone": "CET (UTC+1)",
        "visa_info": "Schengen visa for non-EU visitors",
        "tags": ["beach", "architecture", "food", "nightlife", "art", "Gaudí"],
    },
    {
        "id": "dest-new-york",
        "city": "New York City",
        "country": "United States",
        "region": "North America",
        "description": (
            "New York City is the ultimate urban adventure — a city that never sleeps, packed with "
            "world-famous landmarks, iconic neighbourhoods, and an unbeatable energy. From Times Square's "
            "dazzling lights to Central Park's peaceful greenery, the Brooklyn Bridge to the High Line, "
            "NYC offers infinite experiences. Its unmatched restaurant scene spans every cuisine, "
            "while Broadway, museums, and galleries make it a cultural powerhouse."
        ),
        "highlights": "Central Park, Times Square, Brooklyn Bridge, Statue of Liberty, MoMA, High Line, Broadway",
        "best_time": "April to June, September to November",
        "budget_range": "$200–$400/day",
        "language": "English",
        "currency": "US Dollar (USD)",
        "timezone": "EST (UTC-5)",
        "visa_info": "ESTA for Visa Waiver Program countries; visa required otherwise",
        "tags": ["urban", "culture", "food", "entertainment", "shopping", "iconic"],
    },
    {
        "id": "dest-bali",
        "city": "Bali",
        "country": "Indonesia",
        "region": "Southeast Asia",
        "description": (
            "Bali is the Island of the Gods — a lush tropical paradise of rice terraces, ancient temples, "
            "volcanic mountains, and pristine beaches. Whether you're seeking spiritual renewal in Ubud's "
            "yoga retreats, world-class surf on Uluwatu's cliffs, or vibrant nightlife in Seminyak, "
            "Bali delivers. The Balinese culture of offerings, ceremonies, and warm hospitality creates "
            "an unforgettable atmosphere unlike anywhere else on Earth."
        ),
        "highlights": "Ubud Rice Terraces, Tanah Lot Temple, Mount Batur, Uluwatu, Seminyak Beach, Tirta Empul",
        "best_time": "May to September (dry season)",
        "budget_range": "$50–$150/day",
        "language": "Balinese, Indonesian",
        "currency": "Indonesian Rupiah (IDR)",
        "timezone": "WITA (UTC+8)",
        "visa_info": "Visa on arrival for most nationalities (30 days, extendable)",
        "tags": ["beach", "spiritual", "nature", "surf", "culture", "relaxation"],
    },
    {
        "id": "dest-rome",
        "city": "Rome",
        "country": "Italy",
        "region": "Southern Europe",
        "description": (
            "Rome is the Eternal City — a living museum where ancient history and la dolce vita collide. "
            "Wander through the Roman Forum where emperors once walked, toss a coin in the Trevi Fountain, "
            "and marvel at Michelangelo's Sistine Chapel. The Vatican, the Colosseum, and Piazza Navona "
            "are just the beginning. Rome's piazzas, trattorias serving handmade pasta, and centuries of "
            "artistic heritage make every corner a discovery."
        ),
        "highlights": "Colosseum, Vatican Museums, Trevi Fountain, Pantheon, Roman Forum, Piazza Navona",
        "best_time": "April to June, September to October",
        "budget_range": "$120–$250/day",
        "language": "Italian",
        "currency": "Euro (EUR)",
        "timezone": "CET (UTC+1)",
        "visa_info": "Schengen visa for non-EU visitors",
        "tags": ["history", "culture", "food", "art", "architecture", "religion"],
    },
    {
        "id": "dest-london",
        "city": "London",
        "country": "United Kingdom",
        "region": "Northern Europe",
        "description": (
            "London is a world city of extraordinary depth — where royal palaces stand beside cutting-edge "
            "galleries, and centuries of history unfold across iconic neighbourhoods. From the Tower of "
            "London to the Tate Modern, Big Ben to the bustling Borough Market, London captivates with "
            "its diversity, creativity, and culture. World-class theatre, legendary pubs, and a restaurant "
            "scene representing every corner of the globe make it endlessly rewarding."
        ),
        "highlights": "Tower of London, Big Ben, Tate Modern, British Museum, Borough Market, Hyde Park, West End",
        "best_time": "June to August, September",
        "budget_range": "$150–$350/day",
        "language": "English",
        "currency": "British Pound (GBP)",
        "timezone": "GMT (UTC+0) / BST (UTC+1) in summer",
        "visa_info": "Electronic Travel Authorisation (ETA) required for most visitors post-Brexit",
        "tags": ["culture", "history", "theatre", "food", "museums", "royalty"],
    },
    {
        "id": "dest-sydney",
        "city": "Sydney",
        "country": "Australia",
        "region": "Oceania",
        "description": (
            "Sydney is Australia's harbour city — a sun-drenched playground of iconic architecture, "
            "world-famous beaches, and an outdoor lifestyle that's hard to beat. The Sydney Opera House "
            "and Harbour Bridge are unmissable, while Bondi Beach and the Coastal Walk offer natural "
            "splendour. Sydney's cosmopolitan food scene, vibrant neighbourhoods like Surry Hills and "
            "Newtown, and proximity to the Blue Mountains make it a well-rounded destination for every traveller."
        ),
        "highlights": "Sydney Opera House, Harbour Bridge, Bondi Beach, Blue Mountains, Darling Harbour, Manly",
        "best_time": "September to November, March to May",
        "budget_range": "$150–$280/day",
        "language": "English",
        "currency": "Australian Dollar (AUD)",
        "timezone": "AEDT (UTC+11)",
        "visa_info": "eVisitor or ETA required for most nationalities",
        "tags": ["beach", "outdoor", "harbour", "culture", "food", "nature"],
    },
    {
        "id": "dest-marrakech",
        "city": "Marrakech",
        "country": "Morocco",
        "region": "North Africa",
        "description": (
            "Marrakech is a sensory feast — a labyrinthine medina of spice-scented souks, ornate riads, "
            "and vibrant Djemaa el-Fna square where storytellers, musicians, and food vendors create a "
            "spectacle after dark. The city's blend of Berber, Arab, and French influences produces a "
            "unique culture, extraordinary cuisine, and some of the world's most beautiful architecture. "
            "Day trips to the Atlas Mountains and the Sahara Desert add epic adventure."
        ),
        "highlights": "Djemaa el-Fna, Majorelle Garden, Bahia Palace, Medina Souks, Atlas Mountains day trip",
        "best_time": "March to May, September to November",
        "budget_range": "$60–$150/day",
        "language": "Arabic, Berber, French",
        "currency": "Moroccan Dirham (MAD)",
        "timezone": "WET (UTC+1)",
        "visa_info": "Visa-free for many nationalities up to 90 days",
        "tags": ["culture", "history", "food", "markets", "architecture", "adventure"],
    },
    {
        "id": "dest-reykjavik",
        "city": "Reykjavik",
        "country": "Iceland",
        "region": "Northern Europe",
        "description": (
            "Reykjavik is the gateway to Iceland's extraordinary natural wonders — a compact, quirky "
            "capital city surrounded by volcanoes, geysers, glaciers, and waterfalls. Witness the "
            "Northern Lights dancing overhead in winter, or enjoy the midnight sun in summer. The "
            "Golden Circle route, the Blue Lagoon geothermal spa, and black sand beaches at Vik are "
            "highlights of a country that feels otherworldly. Reykjavik's thriving arts scene and "
            "legendary hospitality complete the experience."
        ),
        "highlights": "Northern Lights, Blue Lagoon, Golden Circle, Hallgrímskirkja, Gullfoss Waterfall, Geysir",
        "best_time": "June to August (midnight sun), November to February (Northern Lights)",
        "budget_range": "$200–$400/day",
        "language": "Icelandic, English widely spoken",
        "currency": "Icelandic Króna (ISK)",
        "timezone": "GMT (UTC+0)",
        "visa_info": "Schengen visa for non-EEA visitors",
        "tags": ["nature", "Northern Lights", "adventure", "geothermal", "Arctic", "photography"],
    },
    {
        "id": "dest-cape-town",
        "city": "Cape Town",
        "country": "South Africa",
        "region": "Sub-Saharan Africa",
        "description": (
            "Cape Town is one of the world's most dramatically beautiful cities — set between the iconic "
            "Table Mountain and two oceans. Hike or cable-car to Table Mountain's flat-topped summit, "
            "explore the Cape Peninsula's rugged coastline, and visit the historic Robben Island. "
            "The Winelands of Stellenbosch and Franschhoek are a short drive away, while the V&A "
            "Waterfront buzzes with restaurants, galleries, and the Cape Malay-influenced Bo-Kaap neighbourhood."
        ),
        "highlights": "Table Mountain, Cape Peninsula, Robben Island, V&A Waterfront, Boulders Beach penguins, Cape Winelands",
        "best_time": "November to March (Southern Hemisphere summer)",
        "budget_range": "$80–$180/day",
        "language": "Afrikaans, English, Xhosa (11 official languages)",
        "currency": "South African Rand (ZAR)",
        "timezone": "SAST (UTC+2)",
        "visa_info": "Visa-free for many nationalities up to 30–90 days",
        "tags": ["nature", "wildlife", "wine", "beach", "history", "adventure"],
    },
    {
        "id": "dest-kyoto",
        "city": "Kyoto",
        "country": "Japan",
        "region": "East Asia",
        "description": (
            "Kyoto is Japan's cultural soul — a city of over a thousand temples, traditional geisha "
            "districts, and pristine Zen gardens. Walk the iconic Fushimi Inari Shrine's thousands of "
            "torii gates, explore the bamboo grove of Arashiyama, and witness a tea ceremony in a "
            "historic machiya townhouse. Unlike frenetic Tokyo, Kyoto moves at a contemplative pace, "
            "offering deep immersion into Japan's ancient traditions, philosophy, and aesthetics."
        ),
        "highlights": "Fushimi Inari, Kinkaku-ji (Golden Pavilion), Arashiyama Bamboo Grove, Gion district, Nijo Castle",
        "best_time": "March to May (cherry blossoms), November (autumn colours)",
        "budget_range": "$70–$180/day",
        "language": "Japanese",
        "currency": "Japanese Yen (JPY)",
        "timezone": "JST (UTC+9)",
        "visa_info": "Visa-free for many nationalities up to 90 days",
        "tags": ["temples", "tradition", "culture", "gardens", "geisha", "history"],
    },
]

# ---------------------------------------------------------------------------
# Vector-store helpers (pgvector only)
# ---------------------------------------------------------------------------

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


def get_collection(name: str) -> Any:
    """Get or create a pgvector-backed collection by name."""
    if name not in _pg_collections:
        _pg_collections[name] = _PgVectorCollection(name)
    return _pg_collections[name]


def reset_client() -> None:
    """Reset global vector clients (used in tests)."""
    global _pg_conn
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
    """Produce a stable document ID from arbitrary text."""
    return hashlib.md5(text.encode()).hexdigest()  # noqa: S324


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
# Destination text formatting
# ---------------------------------------------------------------------------


def format_destination_text(dest: dict[str, Any]) -> str:
    """Render a destination dict as a searchable text document."""
    return (
        f"Destination: {dest['city']}, {dest['country']} ({dest['region']})\n"
        f"Description: {dest['description']}\n"
        f"Highlights: {dest['highlights']}\n"
        f"Best time to visit: {dest['best_time']}\n"
        f"Budget: {dest['budget_range']}\n"
        f"Language: {dest['language']}\n"
        f"Currency: {dest['currency']}\n"
        f"Tags: {', '.join(dest['tags'])}"
    )


# ---------------------------------------------------------------------------
# Destination ingestion
# ---------------------------------------------------------------------------


def ingest_destinations(destinations: list[dict[str, Any]]) -> int:
    """Upsert destination profiles into the destinations collection."""
    if not destinations:
        return 0

    collection = get_collection(COLLECTION_DESTINATIONS)
    texts = [format_destination_text(d) for d in destinations]
    embeddings = embed_texts(texts)
    ids = [d["id"] for d in destinations]
    metadatas = [
        {
            "city": d["city"],
            "country": d["country"],
            "region": d["region"],
            "best_time": d["best_time"],
            "budget_range": d["budget_range"],
            "language": d["language"],
            "currency": d["currency"],
            "highlights": d["highlights"],
            "tags": ", ".join(d["tags"]),
            "type": "destination",
        }
        for d in destinations
    ]
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("Upserted %d destination profiles into pgvector", len(destinations))
    return len(destinations)


def seed_destinations() -> None:
    """Seed the destinations collection with hardcoded data if empty."""
    collection = get_collection(COLLECTION_DESTINATIONS)
    if collection.count() >= len(SEED_DESTINATIONS):
        logger.info(
            "destinations collection already populated (%d), skipping seed",
            collection.count(),
        )
        return
    ingest_destinations(SEED_DESTINATIONS)


# ---------------------------------------------------------------------------
# RSS feed crawler
# ---------------------------------------------------------------------------


async def crawl_feeds(feeds: list[str] | None = None) -> int:
    """Crawl travel RSS feeds and upsert article chunks into pgvector.

    Returns the total number of article chunks indexed.
    """
    feeds = feeds or TRAVEL_FEEDS
    collection = get_collection(COLLECTION_ARTICLES)
    total = 0

    for feed_url in feeds:
        logger.info("Crawling travel feed: %s", feed_url)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", feed_url, exc)
            continue

        feed_title = parsed.feed.get("title", feed_url)
        entries = parsed.get("entries", [])[:30]

        for entry in entries:
            entry_id = entry.get("id") or entry.get("link", "")
            if not entry_id:
                continue

            title: str = entry.get("title", "")
            link: str = entry.get("link", "")
            published: str = entry.get("published", "")
            summary_html: str = entry.get("summary", "") or entry.get("description", "")
            summary = strip_html(summary_html)

            full_text = f"{title}. {summary}".strip()
            if not full_text or full_text == ".":
                continue

            chunks = chunk_text(full_text)
            if not chunks:
                continue

            batch_size = 32
            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start : batch_start + batch_size]
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
                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=batch,
                    metadatas=metadatas,
                )
                total += len(batch)

    logger.info("Travel feed crawl complete. %d article chunks indexed.", total)
    return total


# ---------------------------------------------------------------------------
# High-level ingest routines
# ---------------------------------------------------------------------------


async def run_full_ingest(feeds: list[str] | None = None) -> dict[str, int]:
    """Seed destination profiles + crawl travel RSS feeds. Returns summary counts."""
    seed_destinations()
    article_chunks = await crawl_feeds(feeds)
    return {
        "destination_profiles": get_collection(COLLECTION_DESTINATIONS).count(),
        "article_chunks": article_chunks,
    }
