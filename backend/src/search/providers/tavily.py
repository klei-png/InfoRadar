import os
from datetime import datetime,timezone
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
            if r.get("published_date"):
                try:
                    pub = datetime.fromisoformat(
                        r["published_date"]
                    ).astimezone(timezone.utc)
                except Exception:
                    pub = None
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