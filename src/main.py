import asyncio
import logging

import uvicorn

from src.api.app import app
from src.scheduler import build_scheduler
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)


async def main():
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("InforRadar started, %d job(s) scheduled.", len(scheduler.get_jobs()))

    # 阶段 4 会在这里同时启动 FastAPI (uvicorn)，现在是纯调度器进程
    config = uvicorn.Config(app,host="0.0.0.0",port=8000,log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("InforRadar stopped.")
