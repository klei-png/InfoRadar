import asyncio
import logging
from collections import defaultdict
from datetime import datetime


from src.db.connection import get_conn
from src.db.repository import fetch_top_item,save_digest
from src.llm.gateway import chat_with_meta,LLMError
from src.prompts.registry import get_prompt

logger = logging.getLogger(__name__)

PROMPT_VERSION = "digest-v1"
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

async def generate_one(category: str,items: list[dict],date) -> dict:
    user = (
        f"领域: {category}\n日期：{date}\n"
        f"以下是{len(items)}条高分信息 (编号/分数/标题/摘要/链接)：\n\n"
        f"{_render_items(items)}"
    )
    content, meta = await chat_with_meta(
        [{"role": "system", "content": DIGEST_SYSTEM.system},
         {"role": "user","content":user}],
        temperature=0.3,
    )
    return {
        "category":category,
        "content_md":content,
        "item_count":len(items),
        "cost_tokens":meta["prompt_tokens"]+meta["completion_tokens"],
    }

async def generate_safe(category: str,items: list[dict], date) -> dict | None:
    """ generate briefings;if rejected by content review,split in half recursively
        and isolate toxic entries."""
    try:
        return await generate_one(category,items,date)
    except LLMError as e:
        if "rejected" not in str(e):
            raise

        if len(items) == 1:
            logger.warning("moderation-blocked item %s excluded from digest: %s",
                           items[0]["id"],items[0]["title"][:50])
            return None
        mid = len(items) // 2
        logger.info("digest rejected (%d items), splitting: %s",
                    len(items),category)
        left = await generate_safe(category,items[:mid],date)
        right = await generate_safe(category,items[mid:],date)
        parts = [p for p in (left,right) if p]
        if not parts:
            return None
        return {
            "category": category,
            "content_md": "\n\n".join(p["content_md"] for p in parts),
            "item_count": sum(p["item_count"] for p in parts),
            "cost_tokens": sum(p["cost_tokens"] for p in parts),
        }


async def run_digest(min_score: int = 7, hours: int = 24) -> dict:
    conn = get_conn()
    try:
        items = fetch_top_item(conn,min_score=min_score,hours=hours)
    finally:
        conn.close()

    if not items:
        logger.info("no high-score items in window")
        return {"digest":0}
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[it["category"]].append(it)

    today = datetime.now().date()
    conn = get_conn()
    produced = 0
    try:
        for category, group in groups.items():
            if len(group) < MIN_ITEMS:
                logger.info("skip %s: only %d item(s)",category,len(group))
                continue
            try:
                d = await generate_safe(category,group,today)
                save_digest(conn,today,d["category"],d["content_md"],
                            d["item_count"],d["cost_tokens"],PROMPT_VERSION)
                logger.info("digest saved: %s (%d items, %d tokens)",
                            category,d["item_count"],d["cost_tokens"])
                produced += 1
            except LLMError as e:
                logger.error("digest failed for %s: %s",category,e)
    finally:
        conn.close()
    logger.info("digest run done: %d produced", produced)
    return {"digests": produced}



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    print(asyncio.run(run_digest(min_score=7,hours=48)))
