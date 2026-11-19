from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any
import jsonschema

from src.agent.policy import Policy
from src.agent.types import ToolCall, RunContext
from src.tools.base import Tool, ToolResult
from src.tools.registry import ToolRegistry

class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: Policy):
        self._registry = registry
        self._policy = policy

    async def execute(self, call: ToolCall, ctx: RunContext | None = None) -> ToolResult:
        tool = self._registry.get(call.name)
        if tool is None:
            return ToolResult(
                ok=False,
                content=f"未知工具{call.name!r}，可用：{self._registry.names()}",
                error_code="E_TOOL_DENIED",
            )

        try:
            jsonschema.validate(instance=call.arguments, schema=tool.defn.input_schema)
        except jsonschema.ValidationError as e:
            path = "/".join(str(p) for p in e.absolute_path) or "(root)"
            return ToolResult(
                ok=False,
                content=f"参数校验失败{path}: {e.message}",
                error_code="E_TOOL_FAILED",
            )
        denied = self._policy.check(tool)
        if denied is not None:
            return ToolResult(
                ok=False,
                content=f"工具{tool.defn.name}被策略拒绝{denied}",
                error_code=denied,
            )
        #need to optimize the code
        kwargs = dict(call.arguments)
        if "_ctx" in inspect.signature(tool.handler).parameters:
            kwargs["_ctx"] = ctx
        #-------------------------
        try:
            result = await asyncio.wait_for(
                tool.handler(**kwargs), timeout=tool.defn.timeout
            )
        except TimeoutError:
            return ToolResult(
                ok=False,
                content=f"{tool.defn.name}执行超时(>{tool.defn.timeout}s)",
                error_code="E_TOOL_FAILED",
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content=f"{tool.defn.name}执行异常：{e}",
                error_code="E_TOOL_FAILED",
            )
        r = self._sanitize(tool, result)
        return self._check_output_schema(tool,r)

    @staticmethod
    def _sanitize(tool: Tool, result: Any) -> ToolResult:
        r = result if isinstance(result, ToolResult) else ToolResult(
            ok=True, content=json.dumps(result, ensure_ascii=False, default=str)
        )
        if len(r.content) > tool.defn.output_limit:
            r = r.model_copy(
                update={"content":r.content[:tool.defn.output_limit]+"…[truncated]"}
            )
        return r

    @staticmethod
    def _check_output_schema(tool: Tool, r: ToolResult) -> ToolResult:
        """ check output content"""
        if tool.defn.output_schema is None or not r.ok:
            return r
        try:
            parsed = json.loads(r.content)
            jsonschema.validate(instance=parsed,schema=tool.defn.output_schema)
        except (json.JSONDecodeError, jsonschema.ValidationError) as e:
            return ToolResult(
                ok=False,
                content=f"{tool.defn.name}输出不符合output_schema: {e}",
                error_code="E_TOOL_FAILED",
            )
        return r