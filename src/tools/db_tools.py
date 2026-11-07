from src.db.connection import get_conn
from src.db.repository import fetch_candidates_for_agent
from src.tools.base import Tool, register_tool

async def query_candidates(category: str|None = None, limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        items = fetch_candidates_for_agent(conn,limit=limit)
        if category:
            items = [it for it in items if it.get("category")==category]
        return items
    finally:
        conn.close()

register_tool(Tool(
    name="query_candidates",
    description="查询最近24小时内抓取的待处理信息条目，可按分类过滤",
    parameters={
        "type":"object",
        "properties": {
            "category":{"type":"string","enum":["ai","finance"],
                        "description":"信息分类过滤，不传则返回全部"},
            "limit":{"type":"integer","minmun":1,"maximum":100,
                     "description":"返回条数上限，默认20"}
        },
    },
    handler=query_candidates,
))