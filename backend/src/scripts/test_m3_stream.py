"""M3 块③验收：流式输出——文本增量经总线实时推送，内核行为不变。

全离线：假模型分片吐 delta，验证聚合等价性、直播帧、工具轮回退。
"""
import asyncio
import json
import sys

from src.agent.bus import TokenBus
from src.agent.loop import RunExecutor
from src.agent.policy import Policy
from src.agent.status import RunStatus
from src.agent.tool_executor import ToolExecutor
from src.agent.types import RunConfig, ToolCall

from test_m2_loop import (FakeAdapter, MemoryLedger, MemoryStore, calc_tool,
                          resp_call, resp_text)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CONFIG = RunConfig(max_rounds=5, wall_timeout=10.0)


class StreamingAdapter(FakeAdapter):
    """在剧本模型上加流式外衣：文本响应分片吐 delta（模拟打字机）；
    工具调用响应不分片（对应真实现：工具轮回退非流式）。"""
    def __init__(self, responses, calls=None, chunk_size: int = 4,
                 delay: float = 0.0):
        super().__init__(responses, calls)
        self._chunk_size = chunk_size
        self._delay = delay

    async def complete_streaming(self, messages, tools=None, config=None,
                                 on_delta=None):
        r = await self.complete(messages, tools, config)
        if r.content and not r.tool_calls and on_delta is not None:
            for i in range(0, len(r.content), self._chunk_size):
                on_delta(r.content[i:i + self._chunk_size])
                if self._delay:
                    await asyncio.sleep(self._delay)
        return r


def _reg():
    from src.tools.registry import ToolRegistry
    r = ToolRegistry()
    r.register(calc_tool())
    return r


def _make(responses, bus=None, chunk_size=4):
    store, ledger = MemoryStore(), MemoryLedger([])
    rx = RunExecutor(StreamingAdapter(responses, chunk_size=chunk_size),
                     ToolExecutor(_reg(), Policy()), store, ledger,
                     token_bus=bus)
    return rx, store


def test_streaming_aggregation_equals_complete():
    """聚合结果与普通调用完全等价：终答、状态、事件流一致。"""
    rx, store = _make([resp_text("流式终答内容")])
    out = asyncio.run(rx.execute("run-1", "任务", CONFIG))
    assert out.status == RunStatus.DONE
    assert out.final_answer == "流式终答内容"
    assert store.terminal == ("done", None)


def test_token_bus_receives_full_text():
    """订阅者收到的增量拼接 == 完整终答（打字机不丢字）。"""
    bus = TokenBus()
    rx, _ = _make([resp_text("流式终答内容")], bus=bus)
    q = bus.subscribe("run-1")
    asyncio.run(rx.execute("run-1", "任务", CONFIG))
    deltas = []
    while True:
        try:
            deltas.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break
    assert "".join(deltas) == "流式终答内容"
    bus.unsubscribe("run-1", q)


def test_no_subscriber_does_not_block():
    """零订阅者时 publish 是空操作——模型调用永不被直播拖慢。"""
    bus = TokenBus()
    rx, _ = _make([resp_text("无人观看")], bus=bus)
    out = asyncio.run(rx.execute("run-1", "任务", CONFIG))
    assert out.status == RunStatus.DONE          # 无订阅者照常跑完


def test_tool_round_falls_back_no_deltas():
    """工具轮：响应带 tool_calls → 不吐 delta（流式工具调用排除）；
    终答轮才吐。账本/事件流行为与块③之前完全一致。"""
    bus = TokenBus()
    rx, store = _make([resp_call(ToolCall(call_id="c1", name="calc",
                                          arguments={"a": 1, "b": 2})),
                       resp_text("计算完成")], bus=bus)
    q = bus.subscribe("run-1")
    out = asyncio.run(rx.execute("run-1", "算数任务", CONFIG))
    assert out.status == RunStatus.DONE
    deltas = []
    while True:
        try:
            deltas.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break
    assert "".join(deltas) == "计算完成"          # 工具轮零增量，只有终答帧
    types = [e.type.value for e in store.events]
    assert "tool_call" in types and "tool_result" in types
    bus.unsubscribe("run-1", q)


def test_sse_route_streams_token_frames_live():
    """★ 端到端：worker 运行中订阅 SSE——历史事件 + 实时 token 帧混合，
    增量拼接 == 终答全文；终态后流自动关闭。"""
    from src.api.routes import runs as R

    store, ledger = MemoryStore(), MemoryLedger([])
    bus = TokenBus()
    rx = RunExecutor(StreamingAdapter([resp_text("直播流式终答")],
                                      chunk_size=3, delay=0.03),
                     ToolExecutor(_reg(), Policy()), store, ledger,
                     token_bus=bus)
    R.set_kernel_factory(lambda: R.KernelBundle(
        executor=rx, recovery=R.Recovery(store, ledger,
                                         ToolExecutor(_reg(), Policy())),
        store=store, token_bus=bus))
    try:
        async def body():
            from src.api.routes.runs import _worker, run_events
            run_id = await store.create_run("直播任务", CONFIG, "tester")
            worker = asyncio.create_task(
                _worker(await R._bundle(), run_id, "直播任务", CONFIG))
            resp = await run_events(run_id, timeout_s=10)
            chunks: list[str] = []
            async for c in resp.body_iterator:
                chunks.append(c)
            await worker
            text = "".join(chunks)
            assert "event: start" in text        # 历史回放通道
            assert "event: done" in text
            token_deltas = []
            for line in text.split("\n"):
                if line.startswith("data: ") and '"delta"' in line:
                    token_deltas.append(json.loads(line[6:])["delta"])
            assert "".join(token_deltas) == "直播流式终答"   # 直播通道不丢字
        asyncio.run(body())
    finally:
        R.set_kernel_factory(None)
