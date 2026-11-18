from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal
from pydantic import BaseModel, Field

class ToolDefinition(BaseModel):
    name: str = Field(pattern=r"^[a-z_]{3,32}$")
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    permission: Literal["read","write","dangerous"] = "read"
    timeout: float = 20.0
    side_effect: bool = False
    recovery_strategy: Literal["idempotency_key","business_deduplication","manual"] | None = None
    output_limit: int = 8000
    version: str = "1"

class ToolResult(BaseModel):
    ok: bool
    content: str
    error_code: str | None = None

class Tool:
    """ capability unit: contract(defn)+implementation(handler).
        the handler must be async and return a ToolResult"""
    def __init__(self, defn: ToolDefinition, handler: Callable[...,Awaitable[ToolResult]]) -> None:
        self.defn = defn
        self.handler = handler