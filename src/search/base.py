from abc import ABC, abstractmethod
from dataclasses import dataclass,field
from datetime import datetime
from typing import Any,Optional,Type


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    published_at: Optional[datetime] = None
    raw: dict[str,Any] = field(default_factory=dict)

class SearchProvider(ABC):
    name: str = "base"

    def __init__(self,cfg: dict[str,Any]):
        self.cfg = cfg

    @abstractmethod
    async def search(self,session,query:str,
                     since: Optional[datetime]=None,
                     max_results: int = 20) -> list[SearchResult]:
        ...

    async def health_check(self,session) -> bool:
        try:
            results = await self.search(session,query="test",max_results=1)
            return len(results)>0
        except Exception:
            return False

_PROVIDERS: dict[str,Type[SearchProvider]] = {}

def register_provider(cls: Type[SearchProvider]) -> Type[SearchProvider]:
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError(f"provider {cls.__name__} must define a unique 'name'")
    if cls.name in _PROVIDERS and _PROVIDERS[cls.name] is not cls:
        raise ValueError(f"duplicate provider name: {cls.name}")
    _PROVIDERS[cls.name] = cls
    return cls

def build_provider(cfg: dict[str,Any]) -> SearchProvider:
    provider_name = cfg.get("provider")
    if not provider_name:
        raise ValueError("provider cfg missing 'provider' key")

    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(
            f"unknown provider '{provider_name}'; "
            f"available={sorted(_PROVIDERS)}"
        )
    return cls(cfg)

def available_providers() -> list[str]:
    return sorted(_PROVIDERS)
