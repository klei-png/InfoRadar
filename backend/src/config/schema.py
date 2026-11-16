from typing import Any,Optional
from pydantic import BaseModel,ConfigDict, Field, field_validator

VALID_CATEGORIES = frozenset({"ai","finance"})
SUPPORTED_SOURCE_TYPE = "search"

class ConfigError(ValueError):
    pass

class SearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: str = Field(min_length=1)
    query: str = Field(min_length=1)
    max_results: int = Field(default=20,ge=1,le=100)
    depth:Optional[str] = None
    timeout_s: Optional[int] = Field(default=None,ge=1,le=120)

class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1)
    category: str
    type: str
    interval_min: int = Field(ge=1)
    weight: int = Field(ge=0, le=30)
    enabled: bool
    params: SearchParams
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
        return v

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != SUPPORTED_SOURCE_TYPE:
            raise ValueError(f"type must be '{SUPPORTED_SOURCE_TYPE}'")
        return v

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    endpoint: str = Field(min_length=1)
    api_key:str =""
    depth: str = "basic"
    timeout_s: int = Field(default=30, ge=1, le=120)
    max_results: int = Field(default=20, ge=1, le=100)

class ProviderRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str
    api_key: str
    endpoint: str
    depth: str
    timeout_s: int
    max_results: int
