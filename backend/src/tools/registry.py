from __future__ import annotations

from src.tools.base import Tool

DEDUP_MARKERS = {"去重","幂等","dedup","idempot"}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self,tool:Tool) -> Tool:
        d = tool.defn
        if d.name in self._tools:
            raise ValueError(f"重复注册工具：{d.name}")
        if d.side_effect and d.recovery_strategy is None:
            raise ValueError(f"{d.name}: side_effect=True 必须声明 recovery_strategy")
        if not d.side_effect and d.recovery_strategy is not None:
            raise ValueError(f"{d.name}: side_effect=False 不得声明 recovery_strategy")
        if d.recovery_strategy in ("idempotency_key","business_deduplication"):
            if not any(k in d.description.lower() for k in DEDUP_MARKERS):
                raise ValueError(f"{d.name}: {d.recovery_strategy}")

        self._tools[d.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

default_registry = ToolRegistry()
