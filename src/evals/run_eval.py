import asyncio
import json
import logging
from pathlib import Path

from src.agents.scorer import score_item
from src.db.connection import get_conn
from src.db.repository import fetch_items_by_ids
from src.prompts.registry import prompt_version

logger = logging.getLogger(__name__)
GOLDEN = Path(__file__).parent / "golden.jsonl"

async def run_eval() -> dict:
    cases = [json.load(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    conn = get_conn()
    try:
        items = { it["id"] for it in fetch_items_by_ids(conn,[c["item_id"] for c in cases])}
    finally:
        conn.close()

    correct = 0
    results = []
    for c in cases:
        it = items.get(c["item_id"])
        if not it:
            results.append({"item_id":c["item_id"],"error":"not found"})
            continue
        parsed = await score_item(it)
        bucket = "high" if parsed and parsed["model_score"] >= 7 else "low"
        ok = bucket == c["expected_bucket"]
        correct += ok
        results.append({"item_id": c["item_id"],"expected":c["expected_bucket"],
                        "got":bucket,"score":parsed and parsed["model_score"],"ok":ok})
    report = {"prompt_version":prompt_version("score"),
              "total":len(cases),"correct":correct,
              "accuracy":round(correct/max(len(cases),1),2)}
    logger.info("eval report: %s",report)
    print(json.dumps({**report,"detail":results},ensure_ascii=False,indent=2))
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_eval())