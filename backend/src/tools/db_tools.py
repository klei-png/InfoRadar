import json

from src.db.connection import get_conn
from src.db.repository import fetch_candidates_for_agent
from src.tools.base import Tool, ToolDefinition, ToolResult
from src.tools.registry import default_registry

async def query_candidates(category: str|None = None, limit: int = 20) -> ToolResult:
    conn = get_conn()
    try:
        items = fetch_candidates_for_agent(conn,limit=limit)
        if category:
            items = [it for it in items if it.get("category")==category]
        return ToolResult(ok=True, content=json.dumps(items, ensure_ascii=False, default=str))
    finally:
        conn.close()

default_registry.register(Tool(
    defn=ToolDefinition(
    name="query_candidates",
    description="查询最近24小时内抓取的待处理信息条目，可按分类过滤",
    input_schema={
        "type":"object",
        "properties": {
            "category":{"type":"string","enum":["ai","finance"],
                        "description":"信息分类过滤，不传则返回全部"},
            "limit":{"type":"integer","minmun":1,"maximum":100,
                     "description":"返回条数上限，默认20"}
            },
        },
            permission="read",
        ),
        handler=query_candidates,
    ))