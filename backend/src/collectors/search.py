import hashlib
from datetime import datetime
from typing import Optional

from src.collectors.base import BaseCollector,register
from src.config.schema import SourceConfig
from src.models.schema import RawItem
from src.search.base import build_provider
from src.config.resolver import resolve_provider_cfg
from src.config.loader import load_providers

import src.search.providers.tavily  # noqa: F401


@register
class SearchCollector(BaseCollector):
    type_name = "search"

    def __init__(self, source: SourceConfig):
        super().__init__(source)
        provider_cfg = resolve_provider_cfg(source, load_providers())
        self.provider = build_provider(provider_cfg.model_dump())

    async def fetch(self, session, since: Optional[datetime] = None) -> list[RawItem]:
        params = self.cfg.params
        results = await self.provider.search(
            session, params.query, since=since, max_results=params.max_results
        )
        raw_items = []
        for r in results:
            if not r.url:
                continue
            raw_items.append(RawItem(
                source_id=self.cfg.id,
                external_id=hashlib.md5(r.url.encode()).hexdigest(),
                url=r.url,
                title=r.title,
                snippet=r.snippet,
                published_at=r.published_at,
                raw_meta={
                    "provider": self.provider.name,
                    "query": params.query,
                    **(r.raw or {}),
                },
            ))
        return raw_items