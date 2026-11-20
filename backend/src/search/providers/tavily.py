import os
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from src.search.base import SearchProvider,SearchResult,register_provider

@register_provider
class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self,cfg: dict[str,Any]):
        super().__init__(cfg)
        self.endpoint = cfg.get("endpoint","https://api.tavily.com/search")
        self.api_key = cfg.get("api_key") or os.environ.get("TAVILY_API_KEY")

    async def search(self,session,query:str,
                     since: Optional[datetime]=None,
                     max_results: int = 20) -> list[SearchResult]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": self.cfg.get("depth","basic"),
            # topic=news 才会返回 published_date（general 模式不返回），
            # 且结果限定新闻来源，与信息流场景匹配
            "topic": self.cfg.get("topic","news"),
            "include_raw_content": False,
        }
        if since:
            payload["days"] = max(
                (datetime.now(timezone.utc) - since).days,1
            )
        async with session.post(self.endpoint, json=payload,timeout=30) as resp:
            resp.raise_for_status()
            data = await resp.json()
        out = []
        for r in data.get("results",[]):
            pub = None
            raw = r.get("published_date")
            if raw:
                # Tavily 返回两种格式：ISO8601 或 RFC2822（"Wed, 18 Nov 2026 ... GMT"）
                for parser in (datetime.fromisoformat, parsedate_to_datetime):
                    try:
                        pub = parser(raw)
                        break
                    except (ValueError, TypeError):
                        continue
                if pub is not None:
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                    pub = pub.astimezone(timezone.utc)
            out.append(
                SearchResult(
                    url=r.get("url",""),
                    title=r.get("title",""),
                    snippet=r.get("content",""),
                    published_at=pub,
                    raw=r,
                )
            )
        return out