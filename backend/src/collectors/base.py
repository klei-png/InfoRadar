from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Type

from src.config.schema import SourceConfig
from src.models.schema import RawItem, Item


class BaseCollector(ABC):
    type_name: str = "base"

    def __init__(self, source: SourceConfig):
        self.cfg = source

    @abstractmethod
    async def fetch(self, session, since: Optional[datetime] = None) -> list[RawItem]:
        ...

    def normalize(self, raw: RawItem) -> Item:

        return Item(
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=raw.title,
            content=raw.content,
            snippet=raw.snippet,
            published_at=raw.published_at,
            fetched_at=datetime.now(timezone.utc),
            category=self.cfg.category,
            raw_meta=raw.raw_meta,
            low_confidence_time=raw.published_at is None,
        )

    async def health_check(self, session) -> bool:
        try:
            return len(await self.fetch(session)) > 0
        except Exception:
            return False


_REGISTRY: dict[str, Type[BaseCollector]] = {}


def register(cls: Type[BaseCollector]) -> Type[BaseCollector]:
    if not getattr(cls, "type_name", None) or cls.type_name == "base":
        raise ValueError(f"collector {cls.__name__} must define a unique 'type_name'")
    _REGISTRY[cls.type_name] = cls
    return cls


def build_collector(source:SourceConfig) -> BaseCollector:
    cls = _REGISTRY.get(source.type)
    if cls is None:
        raise ValueError(
            f"no collector for type={source.type!r}; registered={sorted(_REGISTRY)}"
        )
    return cls(source)


def registered_types() -> list[str]:
    return sorted(_REGISTRY)