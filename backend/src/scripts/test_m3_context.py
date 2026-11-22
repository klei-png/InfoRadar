"""M3 块①验收：ContextManager 压缩 + E_LOOP_DETECTED 死循环检测（全离线）。"""
import asyncio
import sys

import pytest

from src.agent.context import ContextManager, ContextPolicy, estimate_chars
from src.agent.loop import RunExecutor
from src.agent.policy import Policy
from src.agent.status import RunStatus
from src.agent.tool_executor import ToolExecutor
from src.agent.types import RunConfig, RunState, ToolCall

from test_m2_loop import (FakeAdapter, MemoryLedger, MemoryStore, calc_tool,
                          big_read_tool, resp_call, resp_text)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CONFIG = RunConfig(max_rounds=5, wall_timeout=10.0)


def _make(reg, responses, ctx_mgr=None):
    store = MemoryStore()
    ledger = MemoryLedger([])
    rx = RunExecutor(FakeAdapter(responses), ToolExecutor(reg, Policy()),
                     store, ledger, ctx_mgr=ctx_mgr)
    return rx, store


def _round_msgs(n: int, content: str, call_prefix: str = "c") -> list[dict]:
    """构造 n 轮消息：assistant(tool_calls) + tool 长结果。"""
    msgs = [{"role": "user", "content": "任务"}]
    for i in range(n):
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"id": f"{call_prefix}{i}", "type": "function",
                                     "function": {"name": "big_read",
                                                  "arguments": f'{{"q":"r{i}"}}'}}]})
        msgs.append({"role": "tool", "tool_call_id": f"{call_prefix}{i}",
                     "content": content})
    return msgs


def test_needs_compaction_threshold():
    cm = ContextManager(ContextPolicy(max_context_chars=1000, compress_ratio=0.8))
    small = [{"role": "user", "content": "短任务"}]
    assert cm.needs_compaction(small) is False
    big = _round_msgs(4, "x" * 500)
    assert cm.needs_compaction(big) is True


def test_compact_preserves_structure():
    """前几轮超长 tool 结果被占位替换；assistant/首条 user/最近 2 轮原文不动。"""
    cm = ContextManager(ContextPolicy(max_context_chars=1000, compress_ratio=0.8,
                                      keep_recent_rounds=2))
    state = RunState(run_id="r", messages=_round_msgs(4, "长" * 400))
    result = cm.compact(state)
    assert result is not None
    assert result.compressed_msgs == 2           # 前 2 轮被压缩
    assert result.chars_after < result.chars_before
    msgs = state.messages
    assert msgs[0] == {"role": "user", "content": "任务"}   # 头部不动
    assert "上下文压缩" in msgs[2]["content"]                # 第 1 轮 tool 被占位
    assert "上下文压缩" in msgs[4]["content"]                # 第 2 轮 tool 被占位
    assert msgs[6]["content"] == "长" * 400                  # 第 3 轮原文保留
    assert msgs[8]["content"] == "长" * 400                  # 第 4 轮原文保留
    assert all("tool_calls" in m for m in msgs
               if m["role"] == "assistant")                  # 协议配对完整
    assert estimate_chars(msgs) < result.chars_before        # 体量下降
    # 注：单趟压缩不保证压到阈值之下——Loop 每轮再触发，逐轮收敛（每次都有事件可审计）


def test_compact_skipped_when_few_rounds():
    cm = ContextManager(ContextPolicy(max_context_chars=100, compress_ratio=0.5,
                                      keep_recent_rounds=2))
    state = RunState(run_id="r", messages=_round_msgs(2, "长" * 400))
    assert cm.compact(state) is None             # 轮数 ≤ keep：无可压缩区


def test_loop_detection_rejects_third_identical_call():
    """同签名第 3 次 → E_LOOP_DETECTED fatal；前 2 次正常执行。"""
    reg = _reg()
    rx, store = _make(reg, [resp_call(ToolCall(call_id="c1", name="calc",
                                               arguments={"a": 1, "b": 1}))])
    out = asyncio.run(rx.execute("run-1", "循环任务", CONFIG))
    assert out.status == RunStatus.FAILED
    assert out.error_code == "E_LOOP_DETECTED"
    tool_calls = [e for e in store.events if e.type.value == "tool_call"]
    assert len(tool_calls) == 2                  # 第 3 次没被执行
    assert store.terminal == ("failed", "E_LOOP_DETECTED")


def test_loop_compaction_triggers_with_checkpoint():
    """多轮长结果逼近预算 → 轮首触发 CONTEXT_COMPACTED + 压缩后存档 + 跑到 DONE。"""
    reg = _reg_big_read()
    cm = ContextManager(ContextPolicy(max_context_chars=600, compress_ratio=0.8,
                                      keep_recent_rounds=1,
                                      compress_tool_result_over=50))
    responses = [resp_call(ToolCall(call_id="c1", name="big_read",
                                    arguments={"q": "第一轮"})),
                 resp_call(ToolCall(call_id="c2", name="big_read",
                                    arguments={"q": "第二轮"})),
                 resp_text("研究完成")]
    rx, store = _make(reg, responses, ctx_mgr=cm)
    out = asyncio.run(rx.execute("run-1", "调研任务", CONFIG))
    assert out.status == RunStatus.DONE
    types = [e.type.value for e in store.events]
    assert "context_compacted" in types
    assert len(store.checkpoints) == 3           # round1 末 + round2 末 + 压缩后
    assert store.checkpoints[-1].version == 3
    # 压缩发生在第 3 轮 complete 之前 → 模型看到的已是占位版本
    final_call_msgs = rx._adapter.calls[2]
    assert any(m.get("role") == "tool" and "上下文压缩" in (m.get("content") or "")
               for m in final_call_msgs)


def _reg():
    from src.tools.registry import ToolRegistry
    r = ToolRegistry(); r.register(calc_tool()); return r


def _reg_big_read():
    from src.tools.registry import ToolRegistry
    r = ToolRegistry(); r.register(big_read_tool()); return r
