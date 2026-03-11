#!/usr/bin/env python3
"""Travel RAG ingest worker entrypoint.

Runs one ingest cycle and exits, suitable for Cloud Run Jobs.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from ingest import run_full_ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def _run() -> int:
    logger.info("Starting travel worker ingest")
    summary = await run_full_ingest()
    logger.info("Travel worker ingest complete: %s", summary)
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("Travel worker ingest failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
