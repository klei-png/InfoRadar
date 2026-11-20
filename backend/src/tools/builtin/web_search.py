from __future__ import annotations

import json
from typing import Any

import aiohttp


from src.search.base import build_provider
from src.tools.base import Tool, ToolDefinition, ToolResult

def build_web_search_tool(provider_cfg: dict[str, Any]) -> Tool:
    provider = build_provider({"provider":"tavily", **provider_cfg})

    async def web_search(query: str, max_results: int = 5) -> ToolResult:
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, query, max_results=max_results)
        payload = [
            {
                "url": r.url,
                "title": r.title,
                "snippet": r.published_at.isoformat() if r.published_at else None,
            }
            for r in results
        ]
        return ToolResult(ok=True, content=json.dumps(payload, ensure_ascii=False, default=str))
    return Tool(
        defn=ToolDefinition(
            name="web_search",
            description="联网搜索，返回结果列表（url/title/snippet/发布时间）",
            input_schema={
                "type":"object",
                "required":["query"],
                "properties":{
                    "query":{"type":"string","description":"搜索关键词"},
                    "max_results":{"type":"integer","minimum":1,"maximum":20,
                                   "description":"返回条数，默认5"},
                },
            },
            timeout=30.0,
            permission="read",
        ),
        handler=web_search,
    )
