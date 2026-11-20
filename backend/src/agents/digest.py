import asyncio
import logging
from collections import defaultdict
from datetime import datetime


from src.db.connection import get_conn
from src.db.repository import fetch_top_item,save_digest
from src.llm.gateway import chat_with_meta,LLMError
from src.prompts.registry import get_prompt

logger = logging.getLogger(__name__)

PROMPT_VERSION = "digest-v2"
MIN_ITEMS = 3

DIGEST_SYSTEM = get_prompt("digest")

def _render_items(items: list[dict]) -> str:
    lines = []
    for it in items:
        snippet = (it.get("snippet") or "")[:150]
        lines.append(
            f"[{it['id']}] ({it['model_score']}分) {it['title']}\n"
            f"      摘要: {snippet}\n"
            f"      链接: {it['url']}"
        )
    return "\n".join(lines)

async def generate_one(items: list[dict],date) -> dict:
    user = (
        f"日期：{date}\n"
        f"以下是{len(items)}条高分信息 (编号/分数/标题/摘要/链接)：\n\n"
        f"{_render_items(items)}"
    )
    content, meta = await chat_with_meta(
        [{"role": "system", "content": DIGEST_SYSTEM.system},
         {"role": "user","content":user}],
        temperature=0.3,
    )
    return {
        "content_md":content,
        "item_count":len(items),
        "cost_tokens":meta["prompt_tokens"]+meta["completion_tokens"],
    }

async def generate_safe(items: list[dict], date) -> dict | None:
    """ generate briefings;if rejected by content review,split in half recursively
        and isolate toxic entries."""
    try:
        return await generate_one(items,date)
    except LLMError as e:
        if "rejected" not in str(e):
            raise

        if len(items) == 1:
            logger.warning("moderation-blocked item %s excluded from digest: %s",
                           items[0]["id"],items[0]["title"][:50])
            return None
        mid = len(items) // 2
        logger.info("digest rejected (%d items), splitting: %s",
                    len(items),date)
        left = await generate_safe(items[:mid],date)
        right = await generate_safe(items[mid:],date)
        parts = [p for p in (left,right) if p]
        if not parts:
            return None
        return {
            "content_md": "\n\n".join(p["content_md"] for p in parts),
            "item_count": sum(p["item_count"] for p in parts),
            "cost_tokens": sum(p["cost_tokens"] for p in parts),
        }


async def run_digest(min_score: int = 7, hours: int = 24) -> dict:
    conn = get_conn()
    try:
        # 已在 SQL 层排除 published_at 为空的条目（无法按天分组）
        items = fetch_top_item(conn,min_score=min_score,hours=hours,limit=200)
    finally:
        conn.close()

    if not items:
        logger.info("no high-score items in window")
        return {"digests":0}

    # 按 published_at 所在自然日分组，每天汇总一份 digest（跨领域）
    groups: dict = defaultdict(list)
    for it in items:
        pub = it["published_at"]
        day = pub.date() if isinstance(pub, datetime) else pub
        groups[day].append(it)

    conn = get_conn()
    produced = 0
    try:
        for day, group in sorted(groups.items()):
            if len(group) < MIN_ITEMS:
                logger.info("skip %s: only %d item(s)",day,len(group))
                continue
            try:
                d = await generate_safe(group,day)
                if d is None:  # 全部被内容审核拦截
                    logger.info("digest empty after moderation: %s",day)
                    continue
                save_digest(conn,day,"all",d["content_md"],
                            d["item_count"],d["cost_tokens"],PROMPT_VERSION)
                logger.info("digest saved: %s (%d items, %d tokens)",
                            day,d["item_count"],d["cost_tokens"])
                produced += 1
            except LLMError as e:
                logger.error("digest failed for %s: %s",day,e)
    finally:
        conn.close()
    logger.info("digest run done: %d produced", produced)
    return {"digests": produced}



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    print(asyncio.run(run_digest(min_score=7,hours=48)))
