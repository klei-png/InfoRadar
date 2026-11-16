import asyncio
import logging
import sys
import aiohttp
from pathlib import Path

from src.config.loader import load_sources,load_providers
from src.config.resolver import resolve_provider_cfg,enabled_sources
from src.config.schema import ConfigError
from src.search.base import build_provider
import src.search.providers.tavily

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SOURCES_PATH = BASE_DIR / "config" / "sources.yaml"
PROVIDERS_PATH = BASE_DIR / "config" / "search_providers.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("validate")

async def probe_source(session: aiohttp.ClientSession,source,providers):
    try:
        #parse and merge provider parameters
        provider_cfg = resolve_provider_cfg(source,providers)
        provider = build_provider(provider_cfg.model_dump())
        logger.info(f"Testing [{source.id}] query='{source.params.query}'...")
        results = await provider.search(
            session,
            query=source.params.query,
            max_results=1
        )
        if results:
            sample = results[0]
            logger.info(f"[{source.id}] OK. Found: {sample.title[:30]}...")
            return True
        else:
            logger.warning(f"[{source.id}] OK but 0 results returned.")
            return True
    except Exception as e:
        logger.error(f"[{source.id}] FAILED: {type(e).__name__}: {e}")
        return False

async def main():
    try:
        sources = load_sources(SOURCES_PATH)
        providers = load_providers(PROVIDERS_PATH)
        active_sources = enabled_sources(sources)
        if not active_sources:
            logger.warning("No enabled sources found.")
            return

        logger.info(f"Loaded {len(sources)} sources ({len(active_sources)} enabled).")

        # 并发验证
        async with aiohttp.ClientSession() as session:
            tasks = [probe_source(session, s, providers) for s in active_sources]
            results = await asyncio.gather(*tasks)

        # 统计结果
        success_count = sum(results)
        total = len(results)
        logger.info(f"--- Validation Complete: {success_count}/{total} passed ---")

        if success_count < total:
            sys.exit(1)

    except ConfigError as e:
        logger.error(f"Configuration Error:\n{e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during validation")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())