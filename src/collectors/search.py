import hashlib
from datetime import datetime
from typing import Optional

from src.collectors.base import BaseCollector,register
from src.models.schema import RawItem
from src.search.base import build_provider

@register
class SearchCollector(BaseCollector):
    type_name = "search"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.provider = build_provider({
            "provider": cfg["params"]["provider"],
            **cfg["params"],
        })

    async def fetch(self, session, since: Optional[datetime] = None) -> list[RawItem]:
        query = self.cfg["params"]["query"]
        max_results = int(self.cfg["params"].get("max_results", 20))
        results = await self.provider.search(
            session, query, since=since, max_results=max_results
        )
        return [
            RawItem(
                source_id=self.cfg["id"],
                external_id=hashlib.md5(r.url.encode()).hexdigest(),
                url=r.url,
                title=r.title,
                snippet=r.snippet,
                publish_at=r.published_at,
                raw_meta={
                    "provider": self.provider.name,
                    "query": query,
                    **(r.raw or {}),
                },
            )
            for r in results
            if r.url
        ]