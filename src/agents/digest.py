import asyncio
import logging
from collections import defaultdict
from datetime import datetime


from src.db.connection import get_conn
from src.db.repository import fetch_top_item,save_digest
from src.llm.gateway import chat_with_meta,LLMError

logger = logging.getLogger(__name__)

PROMPT_VERSION = "digest-v1"
MIN_ITEMS = 3

DIGEST_SYSTEM = """
你是资讯编辑，把同一领域一天内的多条信息整合成一份简报。
要求：
1. 用 Markdown，开头一段 2-3 句的"今日综述"，概括整体动向
2. 按主题分节，重要事件在前；同一事件的多条信息合并为一条，不要重复
3. 每条信息末尾用 [编号] 标注来源条目编号
4. 语言精炼，总长度控制在 500 字以内
5. 直接输出正文，不要任何前后缀说明
"""

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
        [{"role": "system", "content": DIGEST_SYSTEM},
         {"role": "user","content":user}],
        temperature=0.3,
    )
    return {
        "category":category,
        "content_md":content,
        "item_count":len(items),
        "cost_tokens":meta["prompt_tokens"]+meta["completion_tokens"],
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
        groups[it["categroy"]].append(it)

    today = datetime.now().date()
    conn = get_conn()
    produced = 0
    try:
        for category, group in groups.items():
            if len(group) < MIN_ITEMS:
                logger.info("skip %s: only %d item(s)",category,len(group))
                continue
            try:
                d = await generate_one(category,group,today)
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
    print(asyncio.run(run_digest()))
