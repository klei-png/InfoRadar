import asyncio
import json
import logging
import re


from src.db.connection import get_conn
from src.db.repository import fetch_candidates_for_agent, save_scores, mark_items_status
from src.llm.gateway import chat, LLMError

logger = logging.getLogger(__name__)
blocked: list[int] = []

PROMPT_VERSION = "scorer -v1"
SYSTEM_PROMPT = """你是信息质量评估员，评估一条信息对追踪其所属领域动态的价值。
评分维度：
1. 主题相关性：是否真实属于所给分类的核心话题
2. 信息增量：是否有新事实/新发布/新数据，还是营销软文、内容农场、商品页
3. 时效性：是否是新发生的事件

评分标准（0-10 整数）：
- 9-10：权威来源的重大新事件/新发布
- 7-8：有实质信息增量的正常新闻
- 4-6：相关但信息量有限
- 1-3：相关性弱、软文或低质内容
只输出 JSON：{"score": 整数, "reason": "不超过50字的理由"}"""

_JSON_RE = re.compile(r"\{.*\}",re.DOTALL) # possible bug: if multiple '{' appear

def _parse_score(text: str) -> dict | None:
    """ fault-tolerant parsing model output: compatible with json wrapping and extra text"""
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group())
        score = max(1, min(10, int(data["score"])))
        reason = str(data.get("reason",""))[:200]
        return {"score": score,"reason":reason}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None

async def score_item(item: dict) -> dict | None:
    user = (
        f"分类：{item['category']}\n"
        f"标题：{item['title']}\n"
        f"摘要：{item.get('snippet') or '(无)'}\n"
        f"URL：{item['url']}"
    )
    resp = await chat(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role":"user","content":user}],
        json_mode=True
    )
    parsed = _parse_score(resp)
    if parsed is None:
        logger.warning("unparseable score for item %s: %.80s", item["id"],resp)
        return None
    return {"item_id":item["id"],"model_score":parsed["score"],
            "reason":parsed["reason"]}

async def run_scoring(limit: int = 40, concurrency: int = 5) -> dict:
    conn = get_conn()
    try:
        candidates = fetch_candidates_for_agent(conn,limit=limit)
    finally:
        conn.close()
    if not candidates:
        logger.info("no candidates to score")
        return {"scored":0}

    logger.info(f"scoring {len(candidates)} candidate(s), concurrency={concurrency}")
    sem = asyncio.Semaphore(concurrency)

    async def one(it: dict):
        async with sem:
            try:
                return await score_item(it)
            except LLMError as e:
                logger.error("score failed for item %s: %s",it["id"],e)
                blocked.append(it["id"])
                return None
    results = [r for r in await asyncio.gather(*(one(c) for c in candidates)) if r]

    conn = get_conn()
    try:
        saved = save_scores(conn, results)
        if blocked:
            mark_items_status(conn,blocked,"blocked")
            logger.info("marked %d item(s) as blocked", len(blocked))
    finally:
        conn.close()

    logger.info("scoring done: scored=%d/%d",saved,len(candidates))
    return {"scored":saved, "candidates": len(candidates)}

if __name__=="__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    print(asyncio.run(run_scoring()))