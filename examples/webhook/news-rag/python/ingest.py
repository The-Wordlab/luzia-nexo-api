#!/usr/bin/env python3
"""
Standalone RSS feed crawler + pgvector ingestion script.

Run this once to pre-populate the vector index before starting the server,
or invoke it from a cron job / Cloud Scheduler to keep the index fresh.

Usage:
    python ingest.py

All configuration is read from the same environment variables as server.py:
    NEWS_FEEDS               Comma-separated RSS URLs
    EMBEDDING_MODEL          litellm embedding model string
    GOOGLE_CLOUD_PROJECT     Optional source for Vertex project defaults
    GOOGLE_CLOUD_LOCATION    Optional source for Vertex region defaults
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    # Import after logging is configured so server.py's module-level
    # basicConfig call doesn't clobber the format we set above.
    from server import crawl_and_index_feeds, NEWS_FEEDS

    logger.info("Starting ingestion for %d feed(s):", len(NEWS_FEEDS))
    for url in NEWS_FEEDS:
        logger.info("  %s", url)

    stats = await crawl_and_index_feeds()

    logger.info("Ingestion complete.")
    logger.info("  Chunks indexed : %d", stats["num_chunks"])
    logger.info("  Last refresh   : %s", stats["last_refresh"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(0)
