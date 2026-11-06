import asyncio
import logging
import time

import aiohttp

import src.collectors.search  # noqa: F401  触发 SearchCollector 注册
from src.collectors.base import build_collector
from src.config.loader import load_sources
from src.config.resolver import enabled_sources
from src.db.connection import get_conn, init_db
from src.db.repository import insert_items

logger = logging.getLogger(__name__)


async def _fetch_source(session: aiohttp.ClientSession, source, since=None):
    t0 = time.monotonic()
    try:
        collector = build_collector(source)
        raws = await collector.fetch(session, since=since)
        items = [collector.normalize(r) for r in raws]
        logger.info("source %s: %d items in %.1fs",
                    source.id, len(items), time.monotonic() - t0)
        return items
    except Exception:
        logger.exception("source %s fetch failed", source.id)
        return []

async def run_sources(sources) -> dict:
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *(_fetch_source(session,s) for s in sources)
        )
    items = [it for lst in results for it in lst]
    conn = get_conn()
    try:
        inserted = insert_items(conn,items)
    finally:
        conn.close()
    logger.info("run done: fetched=%d inserted=%d", len(items), inserted)
    return {"sources": len(sources), "fetched": len(items), "inserted": inserted}

async def run_once(since=None) -> dict:
    return run_source(enabled_sources(load_sources()))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    print(asyncio.run(run_once()))
