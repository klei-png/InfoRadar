from __future__ import annotations

from src.tools.base import Tool


class Policy:
    def __init__(self, allowed_tools: list[str] | None = None) -> None:
        # None=No whitelist configured: everything except dangerous is allowed
        self._allowed = set(allowed_tools) if allowed_tools is not None else None

    def check(self, tool: Tool) -> str | None:
        """ None=allowed;error=denied.runtime denial goes through TOOL_DENIED fallback"""
        if self._allowed and tool.defn.name not in self._allowed:
            return "E_TOOL_DENIED"
        if tool.defn.permission == "dangerous":
            return "E_TOOL_DENIED"

        return None