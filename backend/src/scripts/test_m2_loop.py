"""M2 块③验收：全部用 fake（不碰 DB/真模型），专注 Loop 的控制流正确性。"""
import asyncio
import sys

import pytest

from src.agent.loop import RunExecutor, RunOutcome
from src.agent.policy import Policy
from src.agent.status import RunStatus
from src.agent.tool_executor import ToolExecutor
from src.agent.types import RunConfig, ToolCall, Usage
from src.llm.adapter import ModelResponse
from src.tools.base import Tool, ToolDefinition, ToolResult
from src.tools.registry import ToolRegistry

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ---------- fakes ----------

class FakeAdapter:
    """按剧本吐响应；耗尽后重复最后一个。记录每次收到的 messages。"""
    def __init__(self, responses: list[ModelResponse], calls: list | None = None):
        self._responses = responses
        self._i = 0
        self.calls = calls if calls is not None else []

    async def complete(self, messages, tools=None, config=None) -> ModelResponse:
        self.calls.append(list(messages))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r


class MemoryStore:
    """RunStore 协议的内存实现：seq 分配/CAS 终态/记录调用轨迹。"""
    def __init__(self, fail_events: bool = False):
        self.fail_events = fail_events
        self.events: list = []
        self.msgs: list = []
        self.checkpoints: list = []
        self.meta: dict = {}
        self.terminal: tuple | None = None

    async def append_events(self, run_id, events):
        if self.fail_events:
            raise RuntimeError("db down")
        for e in events:
            self._seq = getattr(self, "_seq", 0) + 1
            e.seq = self._seq
            self.events.append(e)

    async def append_messages(self, run_id, msgs, checkpoint):
        self.msgs.extend(msgs)

    async def save_checkpoint(self, cp):
        self.checkpoints.append(cp)

    async def load_checkpoint(self, run_id):
        return self.checkpoints[-1] if self.checkpoints else None

    async def save_run_meta(self, run_id, **fields):
        self.meta.update(fields)

    async def transition_terminal(self, run_id, status, error_code=None):
        if self.terminal is not None:
            return False
        self.terminal = (status.value, error_code)
        return True

    async def get_event(self, run_id, seq):
        return next((e for e in self.events if e.seq == seq), None)

    async def create_run(self, task, config, owner):
        return "fake-run"


class MemoryLedger:
    def __init__(self, log: list):
        self.log = log          # 共享轨迹：['create:...', 'exec', 'finish', ...]
        self.records: dict = {}

    async def create_execution(self, run_id, tool_name, idem_key, args_digest):
        self.log.append(f"create:{idem_key[:8]}")
        key = (run_id, idem_key)
        if key not in self.records:
            self.records[key] = {"id": len(self.records) + 1, "status": "pending"}
        return self.records[key]["id"]

    async def start_attempt(self, execution_id):
        self.log.append(f"start:{execution_id}")
        for r in self.records.values():
            if r["id"] == execution_id:
                r["status"] = "executing"      # 与 PG 版一致：attempt 在途 → executing
        return execution_id * 10 + 1

    async def finish_attempt(self, attempt_id, ok, result_digest, error_code):
        self.log.append(f"finish:{attempt_id}:{'ok' if ok else 'fail'}")

    async def complete_execution(self, execution_id, status, result_digest):
        self.log.append(f"complete:{execution_id}:{status}")
        for r in self.records.values():
            if r["id"] == execution_id:
                r["status"] = status           # 与 PG 版一致：终态落账

    async def mark_unknown(self, execution_id):
        self.log.append(f"unknown:{execution_id}")

    async def get_execution(self, run_id, idem_key):
        return self.records.get((run_id, idem_key))


def calc_tool() -> Tool:
    async def handler(a: int, b: int, op: str = "+") -> ToolResult:
        return ToolResult(ok=True, content=str(a + b if op == "+" else a * b))
    return Tool(defn=ToolDefinition(name="calc", description="加法工具",
                                    input_schema={"type": "object", "required": ["a", "b"],
                                                  "properties": {"a": {"type": "integer"},
                                                                 "b": {"type": "integer"}}}),
                handler=handler)


def write_tool(log: list) -> Tool:
    async def handler(text: str) -> ToolResult:
        log.append("exec")
        return ToolResult(ok=True, content=f"written:{text}")
    return Tool(defn=ToolDefinition(name="write_note", description="写外部笔记",
                                    permission="write", side_effect=True,
                                    recovery_strategy="manual",
                                    input_schema={"type": "object", "required": ["text"],
                                                  "properties": {"text": {"type": "string"}}}),
                handler=handler)


def slow_write_tool() -> Tool:
    async def handler(text: str) -> ToolResult:
        await asyncio.sleep(5)          # 模拟外部副作用挂死
        return ToolResult(ok=True, content="never")
    return Tool(defn=ToolDefinition(name="write_note", description="写外部笔记",
                                    permission="write", side_effect=True,
                                    recovery_strategy="manual",
                                    input_schema={"type": "object", "required": ["text"],
                                                  "properties": {"text": {"type": "string"}}}),
                handler=handler)


def big_read_tool() -> Tool:
    async def handler(q: str) -> ToolResult:
        return ToolResult(ok=True, content="证据正文" * 150)   # 600 字
    return Tool(defn=ToolDefinition(name="big_read", description="长文读取",
                                    input_schema={"type": "object", "required": ["q"],
                                                  "properties": {"q": {"type": "string"}}}),
                handler=handler)


def resp_text(text: str) -> ModelResponse:
    return ModelResponse(content=text, tool_calls=[], usage=Usage(prompt_tokens=10,
                         completion_tokens=5), model_version="fake")


def resp_call(tc: ToolCall, usage: Usage | None = None) -> ModelResponse:
    return ModelResponse(content="", tool_calls=[tc],
                         usage=usage or Usage(prompt_tokens=100, completion_tokens=20),
                         model_version="fake")


def make_harness(registry, responses, log=None):
    store, ledger_log = MemoryStore(), (log if log is not None else [])
    ledger = MemoryLedger(ledger_log)
    rx = RunExecutor(FakeAdapter(responses), ToolExecutor(registry, Policy()),
                     store, ledger)
    return rx, store, ledger_log


async def _run(rx, task="测试任务", config=None):
    return await rx.execute("run-1", task, config or RunConfig(max_rounds=3,
                            wall_timeout=10.0))


# ---------- tests ----------

def test_happy_path_done_with_tool_round():
    reg = ToolRegistry(); reg.register(calc_tool())
    responses = [resp_call(ToolCall(call_id="c1", name="calc",
                                    arguments={"a": 2, "b": 3})),
                 resp_text("结果是 5")]
    rx, store, ledger_log = make_harness(reg, responses)
    out = asyncio.run(_run(rx))
    assert out.status == RunStatus.DONE and out.final_answer == "结果是 5"
    assert out.rounds == 2
    assert store.terminal == ("done", None)
    types = [e.type.value for e in store.events]
    assert {"start", "round_start", "tool_call", "tool_result",
            "round_end", "done"} <= set(types)
    # 消息协议配对：assistant(tool_calls) 紧跟 tool 回灌
    assert any(m.get("tool_calls") for m in store.msgs)
    assert any(m.get("role") == "tool" and m.get("content") == "5" for m in store.msgs)
    # checkpoint：round1 后存档，锚定 ROUND_END 的 seq（"倒数第二个"在多轮下会漂移）
    assert len(store.checkpoints) == 1
    assert store.checkpoints[0].version == 1
    round_end_seq = next(e.seq for e in store.events
                         if e.type.value == "round_end")
    assert store.checkpoints[0].last_event_seq == round_end_seq
    assert ledger_log == []                     # 只读工具不进 Ledger


def test_side_effect_write_ahead_before_exec():
    reg = ToolRegistry(); log: list = []
    reg.register(write_tool(log))
    responses = [resp_call(ToolCall(call_id="c1", name="write_note",
                                    arguments={"text": "hi"})),
                 resp_text("done")]
    rx, store, ledger_log = make_harness(reg, responses, log)
    out = asyncio.run(_run(rx))
    assert out.status == RunStatus.DONE
    # log 与 ledger_log 是同一个列表：完整顺序断言（write-ahead 铁律）
    assert ledger_log[0].startswith("create:")               # ★ ① 登记
    assert ledger_log[1].startswith("start:")                # ★ ② 开 attempt
    assert ledger_log[2] == "exec"                           # ★ ③ 副作用最后才执行
    assert ledger_log[3].startswith("finish:")               # ④ 回填尝试结果
    assert ledger_log[4].startswith("complete:1:succeeded")  # ⑤ 落执行终态
    assert ledger_log.index("exec") > ledger_log.index(ledger_log[0])
    # TOOL_RESULT 事件带全文（Evidence content_ref 的数据源）
    tr = next(e for e in store.events if e.type.value == "tool_result")
    assert tr.data["content"] == "written:hi"


def test_dangerous_denied_fed_back_and_run_continues():
    reg = ToolRegistry()
    reg.register(Tool(defn=ToolDefinition(name="nuke_all", description="危险操作",
                                          permission="dangerous",
                                          input_schema={"type": "object",
                                                        "properties": {}}),
                       handler=lambda: None))
    reg.register(calc_tool())
    responses = [resp_call(ToolCall(call_id="c1", name="nuke_all", arguments={})),
                 resp_call(ToolCall(call_id="c2", name="calc",
                                    arguments={"a": 1, "b": 1})),
                 resp_text("改用加法完成")]
    rx, store, _ = make_harness(reg, responses)
    out = asyncio.run(_run(rx))
    assert out.status == RunStatus.DONE
    denied = [e for e in store.events if e.type.value == "tool_denied"]
    assert len(denied) == 1
    # 拒绝结果回灌了模型（第 2 次调用时 messages 里含拒绝文案）
    assert any("被策略拒绝" in m.get("content", "")
               for m in rx._adapter.calls[1])


def test_fail_stop_on_critical_event_persist_failure():
    reg = ToolRegistry(); reg.register(calc_tool())
    responses = [resp_call(ToolCall(call_id="c1", name="calc",
                                    arguments={"a": 1, "b": 1}))]
    store = MemoryStore(fail_events=True)
    rx = RunExecutor(FakeAdapter(responses), ToolExecutor(reg, Policy()),
                     store, MemoryLedger([]))
    out = asyncio.run(rx.execute("run-1", "t", RunConfig(wall_timeout=5)))
    assert out.error_code == "E_PERSIST_FAILED"      # ★ fail-stop
    assert store.terminal is None                    # ★ 不写终态（DB 可能已不可用）


def test_budget_exceeded_fails():
    reg = ToolRegistry(); reg.register(calc_tool())
    responses = [resp_call(ToolCall(call_id="c1", name="calc",
                                    arguments={"a": 1, "b": 1})),
                 resp_text("x")]
    rx, store, _ = make_harness(reg, responses)
    out = asyncio.run(_run(rx, config=RunConfig(max_rounds=3, wall_timeout=10,
                                                token_budget=10)))
    assert out.status == RunStatus.FAILED and out.error_code == "E_BUDGET_EXCEEDED"
    assert store.terminal == ("failed", "E_BUDGET_EXCEEDED")


def test_wall_timeout_with_side_effect_in_flight_marks_unknown():
    reg = ToolRegistry(); reg.register(slow_write_tool())
    responses = [resp_call(ToolCall(call_id="c1", name="write_note",
                                    arguments={"text": "hi"}))]
    rx, store, ledger_log = make_harness(reg, responses)
    out = asyncio.run(_run(rx, config=RunConfig(max_rounds=3, wall_timeout=0.3)))
    assert out.status == RunStatus.NEEDS_ATTENTION           # 暂停态，非终态
    assert out.error_code == "E_UNKNOWN_SIDE_EFFECT"
    assert "unknown:1" in ledger_log                         # Ledger 标 in-doubt
    assert store.terminal is None                            # 暂停态不进终态
    assert store.meta.get("status") == "needs_attention"
    types = [e.type.value for e in store.events]
    assert "attention_required" in types
