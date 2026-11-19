import asyncio

import pytest
from src.agent.policy import Policy
from src.agent.tool_executor import ToolExecutor
from src.agent.types import ToolCall
from src.tools.base import Tool, ToolDefinition, ToolResult
from src.tools.registry import ToolRegistry

async def _stub(**_kw) -> ToolResult:
    return ToolResult(ok=True, content="ok")

def _reg() -> ToolRegistry:
    reg = ToolRegistry()

    async def echo(query: str) -> ToolResult:
        return ToolResult(ok=True, content=f"echo: {query}")

    reg.register(Tool(
        defn=ToolDefinition(
            name="echo_tool",description="测试用回声工具",
            input_schema={"type":"object","required":["query"],
                          "properties":{"query":{"type":"string"}}},
            permission="read",
        ),
        handler=echo,
    ))
    return reg

def _run(coro):
    return asyncio.run(coro)

def test_smoke_success():
    r = _run(ToolExecutor(_reg(), Policy()).execute(
        ToolCall(call_id="c1", name="echo_tool", arguments={"query":"hello"})
    ))
    assert r.ok and r.content == "echo: hello"

def test_smoke_missing_param():
    r = _run(ToolExecutor(_reg(), Policy()).execute(
        ToolCall(call_id="c2", name="echo_tool", arguments={})))
    assert not r.ok and "query" in r.content and r.error_code == "E_TOOL_FAILED"

def test_smoke_unknown_tool():
    r = _run(ToolExecutor(_reg(), Policy()).execute(
        ToolCall(call_id="c3", name="nope", arguments={})))
    assert not r.ok and r.error_code == "E_TOOL_DENIED" and "echo_tool" in r.content

def test_smoke_denied_by_policy():
    r = _run(ToolExecutor(_reg(), Policy(allowed_tools=["other"])).execute(
        ToolCall(call_id="c4", name="echo_tool", arguments={"query": "x"})))
    assert not r.ok and r.error_code == "E_TOOL_DENIED"

def test_policy_blocks_dangerous():
    reg = _reg()
    reg.register(Tool(
        defn=ToolDefinition(name="boom_tool", description="危险操作",
                            input_schema={"type": "object", "properties": {}},
                            permission="dangerous"),
        handler=_stub))
    r = _run(ToolExecutor(reg, Policy()).execute(
        ToolCall(call_id="c5", name="boom_tool", arguments={})))
    assert not r.ok and r.error_code == "E_TOOL_DENIED"

def test_registry_rejects_strategy_without_side_effect():
    with pytest.raises(ValueError):
        ToolRegistry().register(Tool(
            defn=ToolDefinition(name="fake_tool", description="x",
                                input_schema={}, recovery_strategy="manual"),
            handler=_stub))

def test_registry_rejects_dedup_without_declaration():
    with pytest.raises(ValueError):
        ToolRegistry().register(Tool(
            defn=ToolDefinition(name="send_email", description="发送邮件",
                                input_schema={}, side_effect=True,
                                recovery_strategy="idempotency_key"),
            handler=_stub))