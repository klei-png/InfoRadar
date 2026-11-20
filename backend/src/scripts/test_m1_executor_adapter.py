import asyncio
import json
from unittest.mock import AsyncMock,MagicMock,patch

from src.agent.policy import Policy
from src.agent.tool_executor import ToolExecutor
from src.agent.types import ModelConfig,RunContext,RunState,ToolCall
from src.llm.adapter import LiteLLMAdapter,ModelAdapterError
from src.tools.base import Tool,ToolDefinition,ToolResult
from src.tools.registry import ToolRegistry

async def _stub(**_kw) -> ToolResult:
    return ToolResult(ok=True, content="ok")

def _run(coro):
    return asyncio.run(coro)

def _reg() -> ToolRegistry:
    reg = ToolRegistry()

    async def stats() -> ToolResult:
        return ToolResult(ok=True, content=json.dumps({"count": 3}))

    reg.register(Tool(
        defn=ToolDefinition(
            name="stats_tool", description="返回统计",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "required": ["count"],
                           "properties": {"count": {"type": "integer"}}},
        ),
        handler=stats,
    ))

    async def peek(_ctx=None) -> ToolResult:  # 声明 _ctx 的工具
        evs = [e.evidence_id for e in _ctx.state.evidence] if _ctx else []
        return ToolResult(ok=True, content=json.dumps({"evidence": evs}))

    reg.register(Tool(
        defn=ToolDefinition(name="peek_tool", description="读上下文证据",
                            input_schema={"type": "object", "properties": {}}),
        handler=peek,
    ))

    return reg

def test_output_schema_pass():
    r = _run(ToolExecutor(_reg(), Policy()).execute(
        ToolCall(call_id="c1", name="stats_tool", arguments={})))
    assert r.ok and json.loads(r.content)["count"] == 3

def test_output_schema_fail():
    reg = _reg()

    async def bad() -> ToolResult:
        return ToolResult(ok=True, content=json.dumps({"count": "not-int"}))

    reg._tools["stats_tool"].handler = bad
    r = _run(ToolExecutor(reg, Policy()).execute(
        ToolCall(call_id="c2", name="stats_tool", arguments={})))
    assert not r.ok and "output_schema" in r.content

def test_ctx_injection():
    ctx = RunContext(run_id="r1", state=RunState(run_id="r1"))
    r = _run(ToolExecutor(_reg(), Policy()).execute(
        ToolCall(call_id="c3", name="peek_tool", arguments={}), ctx=ctx))
    assert json.loads(r.content)["evidence"] == []

# ---- ModelAdapter ----

def _fake_response(content=None, tool_calls=None, pt=10, ct=5):
    resp = MagicMock()
    resp.usage.prompt_tokens, resp.usage.completion_tokens = pt, ct
    msg = MagicMock()
    msg.content, msg.tool_calls = content, tool_calls
    resp.choices = [MagicMock(message=msg)]
    return resp

def test_adapter_plain_completion():
    adapter = LiteLLMAdapter(ModelConfig(max_retries=1))
    with patch("src.llm.adapter.litellm.acompletion",
               new=AsyncMock(return_value=_fake_response(content="hello"))):
        r = _run(adapter.complete([{"role": "user", "content": "hi"}]))
    assert r.content == "hello" and r.tool_calls == []
    assert r.usage.prompt_tokens == 10

def test_adapter_normalizes_tool_calls():
    tc = MagicMock()
    tc.id, tc.function.name = "call_1", "web_search"
    tc.function.arguments = json.dumps({"query": "ai news"})
    adapter = LiteLLMAdapter(ModelConfig(max_retries=1))
    with patch("src.llm.adapter.litellm.acompletion",
               new=AsyncMock(return_value=_fake_response(tool_calls=[tc]))):
        r = _run(adapter.complete([], tools=[]))
    assert r.tool_calls[0].call_id == "call_1"
    assert r.tool_calls[0].arguments == {"query": "ai news"}

def test_adapter_bad_json_retries_then_fails():
    tc = MagicMock()
    tc.id, tc.function.name, tc.function.arguments = "call_1", "x", "{invalid"
    adapter = LiteLLMAdapter(ModelConfig(max_retries=1))
    with patch("src.llm.adapter.litellm.acompletion",
               new=AsyncMock(return_value=_fake_response(tool_calls=[tc]))):
        try:
            _run(adapter.complete([]))
            assert False, "应抛 ModelAdapterError"
        except ModelAdapterError as e:
            assert "E_MODEL_UNAVAILABLE" in str(e)

def test_adapter_retries_on_429_then_succeeds():
    import litellm
    adapter = LiteLLMAdapter(ModelConfig(max_retries=2))
    mock = AsyncMock(side_effect=[
        litellm.exceptions.RateLimitError("429", "rate", "glm"),
        _fake_response(content="ok"),
    ])
    with patch("src.llm.adapter.litellm.acompletion", new=mock):
        r = _run(adapter.complete([]))
    assert r.content == "ok" and mock.call_count == 2