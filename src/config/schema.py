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
