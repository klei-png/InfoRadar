import asyncio
import logging

import uvicorn

from src.api.app import app
from src.scheduler import build_scheduler
from src.api.auth import AUTH_PASSWORD, AUTH_SECRET
from src.db.connection import get_conn
from src.db.repository import ensure_user_table, count_users, create_user
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)


def bootstrap_auth():
    """启动时建 users 表；表空且配置了 AUTH_PASSWORD 则创建默认用户 admin"""
    if not AUTH_SECRET:
        logger.warning("AUTH_SECRET not set, auth disabled.")
        return
    conn = get_conn()
    try:
        ensure_user_table(conn)
        if count_users(conn) == 0 and AUTH_PASSWORD:
            create_user(conn, "admin", AUTH_PASSWORD)
            logger.info("default user 'admin' created from AUTH_PASSWORD")
    finally:
        conn.close()


async def main():
    bootstrap_auth()
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
