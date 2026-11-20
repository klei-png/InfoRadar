from __future__ import annotations

import json

from src.db.connection import get_conn
from src.db.repository import semantic_search
from src.llm.gateway import embed
from src.pipeline.embedding import vector_to_str
from src.tools.base import Tool,ToolDefinition,ToolResult


def build_kb_search_tool() -> Tool:
    async def kb_search(query: str, limit: int = 5, category: str | None = None) -> ToolResult:
        vecs = await embed([query])
        conn = get_conn()
        try:
            rows = semantic_search(conn,vector_to_str(vecs[0]),
                                   limit=limit,category=category)
        finally:
            conn.close()
        payload = [
            {
                "id":r["id"],
                "title":r["title"],
                "url":r["url"],
                "snippet":(r["snippet"] or "")[:300],
                "similarity": round(float(r["similarity"]),3),
            }
            for r in rows
        ]
        return ToolResult(ok=True,content=json.dumps(payload, ensure_ascii=False,default=str))

    return Tool(
        defn=ToolDefinition(
            name="kb_search",
            description="在本地知识库中按语义相似度检索已抓取的信息条目",
            input_schema={
                "type":"object",
                "required":["query"],
                "properties":{
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "category": {"type": "string", "enum": ["ai", "finance"]},
                },
            },
            timeout=30.0,
            permission="read",
        ),
        handler=kb_search,
    )