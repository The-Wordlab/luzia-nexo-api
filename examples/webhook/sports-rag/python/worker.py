#!/usr/bin/env python3
"""Sports RAG ingest worker entrypoint.

Runs one ingest cycle and exits, suitable for Cloud Run Jobs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from ingest import run_full_ingest, run_live_ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def _run() -> int:
    mode = os.environ.get("SPORTS_WORKER_MODE", "live").strip().lower()
    logger.info("Starting sports worker ingest (mode=%s)", mode)

    if mode == "full":
        summary = await run_full_ingest()
    elif mode == "live":
        summary = await run_live_ingest()
    else:
        logger.error("Invalid SPORTS_WORKER_MODE: %s (expected: live|full)", mode)
        return 2

    logger.info("Sports worker ingest complete: %s", summary)
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("Sports worker ingest failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
