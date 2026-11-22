"""M2 块④验收：崩溃恢复决策树 + write-ahead 存档 + pending 重放（全离线 fake）。"""
import asyncio
import hashlib
import sys

import pytest

from src.agent.policy import Policy
from src.agent.loop import RunExecutor
from src.agent.recovery import Recovery
from src.agent.status import RunStatus
from src.agent.tool_executor import ToolExecutor
from src.agent.types import Checkpoint, RunConfig, RunState, ToolCall
from src.tools.base import Tool, ToolDefinition, ToolResult
from src.tools.registry import ToolRegistry

from test_m2_loop import (FakeAdapter, MemoryLedger, MemoryStore, calc_tool,
                          resp_call, resp_text, write_tool)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ---------- 本文件专用的幂等写工具（description 必须含去重声明，过 Registry 第 5 闸） ----------

def idem_write_tool(log: list) -> Tool:
    async def handler(text: str) -> ToolResult:
        log.append("exec")
        return ToolResult(ok=True, content=f"written:{text}")
    return Tool(defn=ToolDefinition(
        name="write_note", description="写外部笔记（幂等键去重保护，重放安全）",
        permission="write", side_effect=True, recovery_strategy="idempotency_key",
        input_schema={"type": "object", "required": ["text"],
                      "properties": {"text": {"type": "string"}}}),
        handler=handler)


# ---------- 测试脚手架 ----------

def _idem_key(run_id: str, call_id: str) -> str:
    return hashlib.sha256(f"{run_id}{call_id}".encode()).hexdigest()


def _seed_checkpoint(store: MemoryStore, run_id: str, config: RunConfig,
                     pending: list[ToolCall]) -> None:
    state = RunState(run_id=run_id, config_snapshot=config.model_dump(),
                     messages=[{"role": "user", "content": "写笔记"}])
    store.checkpoints.append(Checkpoint(run_id=run_id, version=1, last_event_seq=2,
                                        state=state, pending_tool_calls=list(pending)))


async def _seed_in_flight(ledger: MemoryLedger, run_id: str, tc: ToolCall) -> int:
    """模拟崩溃现场：write-ahead 已登记、attempt 在途、无回填（进程在这里死了）。"""
    eid = await ledger.create_execution(run_id, tc.name,
                                        _idem_key(run_id, tc.call_id), "d")
    await ledger.start_attempt(eid)
    return eid


def _make(reg, responses, log):
    store = MemoryStore()
    ledger_log: list = []
    ledger = MemoryLedger(ledger_log)
    rx = RunExecutor(FakeAdapter(responses), ToolExecutor(reg, Policy()),
                     store, ledger)
    rec = Recovery(store, ledger, ToolExecutor(reg, Policy()))
    return rx, store, ledger, ledger_log


CONFIG = RunConfig(max_rounds=3, wall_timeout=10.0)


# ---------- 恢复决策树 ----------

def test_idempotent_in_flight_resumes_and_replays_second_attempt():
    """崩溃在幂等副作用 attempt 途中 → 重放：同一 execution 加新 attempt，不新建登记。"""
    async def body():
        reg = ToolRegistry(); log: list = []
        reg.register(idem_write_tool(log))
        rx, store, ledger, ledger_log = _make(reg, [resp_text("完成")], log)
        tc = ToolCall(call_id="c9", name="write_note", arguments={"text": "hi"})
        _seed_checkpoint(store, "run-1", CONFIG, [tc])
        eid = await _seed_in_flight(ledger, "run-1", tc)   # ★ 崩溃现场

        plan = await Recovery(store, ledger, ToolExecutor(reg, Policy())).plan(
            "run-1", CONFIG)
        assert plan.action == "resume" and plan.pending == [tc]

        out = await rx.execute("run-1", "写笔记", CONFIG,
                               state=plan.state, pending=plan.pending)
        assert out.status == RunStatus.DONE
        assert len(ledger.records) == 1             # ★ 登记幂等：两次 create 同一 execution
        assert len(starts) == 2                     # ★ 崩溃前 1 次 + 重放 1 次
        assert f"complete:{eid}:succeeded" in ledger_log
        assert any(m.get("role") == "tool" and m.get("content") == "written:hi"
                   for m in store.msgs)             # 重放结果已回灌
    asyncio.run(body())


def test_manual_in_flight_goes_needs_attention():
    """崩溃在 manual 副作用 attempt 途中 → unknown → needs_attention（不重放）。"""
    async def body():
        reg = ToolRegistry(); log: list = []
        reg.register(write_tool(log))               # write_tool 是 manual 策略
        rx, store, ledger, ledger_log = _make(reg, [resp_text("完成")], log)
        tc = ToolCall(call_id="c9", name="write_note", arguments={"text": "hi"})
        _seed_checkpoint(store, "run-1", CONFIG, [tc])
        eid = await _seed_in_flight(ledger, "run-1", tc)

        plan = await Recovery(store, ledger, ToolExecutor(reg, Policy())).plan(
            "run-1", CONFIG)
        assert plan.action == "needs_attention"
        assert plan.error_code == "E_UNKNOWN_SIDE_EFFECT"
        assert f"unknown:{eid}" in ledger_log       # execution 已标 in-doubt
        assert store.meta.get("status") == "needs_attention"
        assert store.terminal is None               # 暂停态不是终态
        assert log == []                            # ★ 副作用没有被执行第二次
    asyncio.run(body())


def test_config_drift_fails_recovery():
    async def body():
        reg = ToolRegistry(); reg.register(calc_tool())
        rx, store, ledger, _ = _make(reg, [resp_text("x")], [])
        _seed_checkpoint(store, "run-1", RunConfig(max_rounds=3, wall_timeout=10.0), [])
        plan = await Recovery(store, ledger, ToolExecutor(reg, Policy())).plan(
            "run-1", RunConfig(max_rounds=9, wall_timeout=10.0))   # 配置漂移
        assert plan.action == "failed" and plan.error_code == "E_RECOVER_CONFIG_DRIFT"
    asyncio.run(body())


def test_no_checkpoint_fails_recovery():
    async def body():
        reg = ToolRegistry(); reg.register(calc_tool())
        rx, store, ledger, _ = _make(reg, [resp_text("x")], [])
        plan = await Recovery(store, ledger, ToolExecutor(reg, Policy())).plan(
            "run-1", CONFIG)
        assert plan.action == "failed" and plan.error_code == "E_RECOVER_FAILED"
    asyncio.run(body())


def test_read_only_pending_replays_without_ledger():
    async def body():
        reg = ToolRegistry(); reg.register(calc_tool())
        rx, store, ledger, ledger_log = _make(reg, [resp_text("完成")], [])
        tc = ToolCall(call_id="c1", name="calc", arguments={"a": 2, "b": 3})
        _seed_checkpoint(store, "run-1", CONFIG, [tc])
        plan = await Recovery(store, ledger, ToolExecutor(reg, Policy())).plan(
            "run-1", CONFIG)
        assert plan.action == "resume"
        out = await rx.execute("run-1", "算数", CONFIG,
                               state=plan.state, pending=plan.pending)
        assert out.status == RunStatus.DONE
        assert any(m.get("role") == "tool" and m.get("content") == "5"
                   for m in store.msgs)
        assert ledger_log == []                     # 只读工具不进 Ledger
    asyncio.run(body())


# ---------- write-ahead 存档（Loop 新行为） ----------

def test_loop_saves_write_ahead_checkpoint_before_side_effect():
    """副作用批次执行前必须有 pending 非空的存档，执行后 round-end 存档清空 pending。"""
    async def body():
        reg = ToolRegistry(); log: list = []
        reg.register(write_tool(log))
        rx, store, ledger, _ = _make(reg, [
            resp_call(ToolCall(call_id="c1", name="write_note",
                               arguments={"text": "hi"})),
            resp_text("done")], log)
        out = await rx.execute("run-1", "写笔记", CONFIG)
        assert out.status == RunStatus.DONE
        assert len(store.checkpoints) == 2
        assert store.checkpoints[0].version == 1
        assert store.checkpoints[0].pending_tool_calls[0].call_id == "c1"   # ★ 事前存档
        assert store.checkpoints[1].version == 2
        assert store.checkpoints[1].pending_tool_calls == []                # 事后清空
    asyncio.run(body())
