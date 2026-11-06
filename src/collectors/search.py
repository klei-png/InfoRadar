import hashlib
from datetime import datetime
from typing import Optional

from src.collectors.base import BaseCollector,register
from src.models.schema import RawItem
from src.search.base import build_provider
from src.config.resolver import resolve_provider_cfg
from src.config.loader import load_providers

import src.search.providers.tavily


@register
class SearchCollector(BaseCollector):
    type_name = "search"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        providers = load_providers()
        if hasattr(cfg, 'params'):
            provider_cfg = resolve_provider_cfg(cfg,providers)
            self.provider = build_provider(provider_cfg.model_dump())
        else:
            self.provider = build_provider({
                "provider": cfg["params"]["provider"],
                **cfg["params"]
            })

    async def fetch(self, session, since: Optional[datetime] = None) -> list[RawItem]:
        if hasattr(self.cfg,'params'):
            params = self.cfg.params
            query = params.query
            source_id = self.cfg.id
            max_results = params.max_results
        else:
            params = self.cfg["params"]
            query = params["query"]
            source_id = self.cfg["id"]
            max_results = int(params.get("max_results", 20))

        results = await self.provider.search(
            session, query, since=since, max_results=max_results
        )
        raw_items = []
        for r in results:
            # <--- 注意 4：修复旧版被遗漏的空 URL 过滤逻辑
            if not r.url:
                continue

            raw_items.append(RawItem(
                source_id=source_id,
                external_id=hashlib.md5(r.url.encode()).hexdigest(),
                url=r.url,
                title=r.title,
                snippet=r.snippet,
                published_at=r.published_at,
                raw_meta={
                    "provider": self.provider.name,
                    "query": query,
                    **(r.raw or {})
                },
            ))
        return raw_items