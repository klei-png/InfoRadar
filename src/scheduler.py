import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from src.agents.scorer import run_scoring
from src.agents.digest import run_digest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config.loader import load_sources
from src.config.resolver import enabled_sources
from src.pipeline.runner import run_sources

logger = logging.getLogger(__name__)

def _make_job(source):

    async def job():
        logger.info(f"scheduled fetch: {source.id}(every {source.interval_min} min)")
        await run_sources([source])
    job.__name__ = f"fetch_{source.id}"
    return job

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        job_defaults = {
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time":300,
        }
    )
    for source in enabled_sources(load_sources()):
        scheduler.add_job(
            _make_job(source),
            trigger=IntervalTrigger(minutes=source.interval_min),
            id=f"fetch_{source.id}",
            name=source.id,
            next_run_time=datetime.now(timezone.utc),
        )
    scheduler.add_job(
        run_scoring,
        trigger=CronTrigger(hour="*/2",minute=10),
        id="agent_scoring",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_digest,
        trigger=CronTrigger(hour=8,minute=40),
        id="agent_digest",
        name="digest",
        max_instances=1,
        coalesce=True,
    )
    return scheduler

async def main():
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler started, %d job(s). Ctrl+C to stop.",
                len(scheduler.get_jobs()))
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler stopped.")