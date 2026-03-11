#!/usr/bin/env python3
"""Football Live ingest worker entrypoint.

Runs one ingest cycle and exits, suitable for Cloud Run Jobs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from football_api import FootballDataClient
from ingest import run_full_ingest, run_live_ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def _run() -> int:
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
    if not api_key:
        logger.error("FOOTBALL_DATA_API_KEY is required for football worker")
        return 2

    mode = os.environ.get("FOOTBALL_WORKER_MODE", "live").strip().lower()
    client = FootballDataClient(api_key)

    logger.info("Starting football worker ingest (mode=%s)", mode)
    if mode == "full":
        summary = await run_full_ingest(client)
    elif mode == "live":
        summary = {"matches_updated": await run_live_ingest(client)}
    else:
        logger.error("Invalid FOOTBALL_WORKER_MODE: %s (expected: live|full)", mode)
        return 2

    logger.info("Football worker ingest complete: %s", summary)
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("Football worker ingest failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
