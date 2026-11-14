import asyncio
import json
import logging
import re


from src.db.connection import get_conn
from src.db.repository import fetch_candidates_for_agent, save_scores, mark_items_status
from src.llm.gateway import chat, LLMError
from src.prompts.registry import get_prompt,prompt_version

logger = logging.getLogger(__name__)
blocked: list[int] = []

SYSTEM_PROMPT = get_prompt("scorer")
PROMPT_VERSION = prompt_version("scorer")

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
        [{"role": "system", "content": SYSTEM_PROMPT.system},
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