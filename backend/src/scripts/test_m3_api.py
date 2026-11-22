"""M3 块②验收：resolve_attention 三裁决（内核）+ /runs 路由（外壳）。

内核测试全离线；路由测试用 TestClient + fake 内核工厂（不碰 DB/真模型）。
"""
import asyncio
import sys
import time

from fastapi.testclient import TestClient

from src.agent.loop import RunExecutor, RunOutcome
from src.agent.policy import Policy
from src.agent.recovery import Recovery
from src.agent.status import RunStatus
from src.agent.tool_executor import ToolExecutor
from src.agent.types import Checkpoint, RunConfig, RunState, ToolCall

from test_m2_loop import (FakeAdapter, MemoryLedger, MemoryStore, write_tool,
                          resp_text)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CONFIG = RunConfig(max_rounds=5, wall_timeout=10.0)
_TC = ToolCall(call_id="c9", name="write_note", arguments={"text": "hi"})


def _seed_paused():
    """构造 needs_attention 崩溃现场：manual 副作用在途 → unknown。"""
    store, ledger = MemoryStore(), MemoryLedger([])
    log: list = []
    reg = _reg(log)
    toolx = ToolExecutor(reg, Policy())
    idem = __import__("hashlib").sha256(b"run-1c9").hexdigest()
    eid = asyncio.run(ledger.create_execution("run-1", "write_note", idem,
                                              "digest"))
    asyncio.run(ledger.start_attempt(eid))
    asyncio.run(ledger.mark_unknown(eid))
    state = RunState(run_id="run-1", config_snapshot=CONFIG.model_dump(),
                     messages=[{"role": "user", "content": "写笔记"}])
    asyncio.run(store.save_checkpoint(Checkpoint(
        run_id="run-1", version=1, last_event_seq=1, state=state,
        pending_tool_calls=[_TC])))
    asyncio.run(store.save_run_meta("run-1",
                                    status=RunStatus.NEEDS_ATTENTION.value))
    rx = RunExecutor(FakeAdapter([resp_text("完成")]), toolx, store, ledger)
    return rx, store, ledger, toolx


def _reg(log):
    from src.tools.registry import ToolRegistry
    r = ToolRegistry()
    r.register(write_tool(log))
    return r


def _reg_for_resume(log):
    """resume 用：同一 log 变量穿透两次 _reg 构造。"""
    return _reg(log)


def test_resolve_succeeded_backfills_and_queues():
    rx, store, ledger, _ = _seed_paused()
    out = asyncio.run(rx.resolve_attention("run-1", "side_effect_succeeded"))
    assert out.status == RunStatus.QUEUED
    rec = next(iter(ledger.records.values()))
    assert rec["status"] == "succeeded"                     # unknown → 人工裁决值
    assert store.terminal is None                           # 非终态，可续跑
    cp = store.checkpoints[-1]
    assert cp.pending_tool_calls == []                      # 清空 → Recovery 不再重放
    assert any(m.get("role") == "tool" and "已确认成功" in m["content"]
               for m in cp.state.messages)                  # 裁决结果已回灌
    assert store.meta["status"] == "queued"


def test_resolve_succeeded_then_resume_no_replay():
    """★ 裁决后续跑：工具不重放（exec 零次），模型拿到裁决消息直接收尾。"""
    rx, store, ledger, toolx = _seed_paused()
    log: list = []
    asyncio.run(rx.resolve_attention("run-1", "side_effect_succeeded"))
    plan = asyncio.run(Recovery(store, ledger, toolx).plan("run-1", CONFIG))
    assert plan.action == "resume" and plan.pending == []
    rx2 = RunExecutor(FakeAdapter([resp_text("完成")]),
                      ToolExecutor(_reg_for_resume(log), Policy()), store, ledger)
    out = asyncio.run(rx2.execute("run-1", "写笔记", CONFIG,
                                  state=plan.state, pending=plan.pending))
    assert out.status == RunStatus.DONE
    assert not any(x == "exec" for x in log)                # ★ 副作用零重放


def test_resolve_failed_backfills_failure():
    rx, store, ledger, _ = _seed_paused()
    out = asyncio.run(rx.resolve_attention("run-1", "side_effect_failed"))
    assert out.status == RunStatus.QUEUED
    rec = next(iter(ledger.records.values()))
    assert rec["status"] == "failed"
    assert any(m.get("role") == "tool" and "确认失败" in m["content"]
               for m in store.checkpoints[-1].state.messages)


def test_resolve_abort_lands_cancelled():
    rx, store, ledger, _ = _seed_paused()
    out = asyncio.run(rx.resolve_attention("run-1", "abort"))
    assert out.status == RunStatus.CANCELLED
    assert store.terminal == ("cancelled", "E_CANCELLED")


def test_resolve_without_checkpoint_fails():
    rx, store, ledger, _ = _seed_paused()
    store.checkpoints.clear()
    out = asyncio.run(rx.resolve_attention("run-1", "side_effect_succeeded"))
    assert out.status == RunStatus.FAILED
    assert out.error_code == "E_RECOVER_FAILED"


#-------------------------routes（TestClient + fake 工厂）-------------------------

def _fake_bundle_factory(store, ledger, log):
    def make():
        reg = _reg(log)
        toolx = ToolExecutor(reg, Policy())
        rx = RunExecutor(FakeAdapter([resp_text("研究完成")]), toolx, store, ledger)
        from src.api.routes.runs import KernelBundle
        return KernelBundle(executor=rx,
                            recovery=Recovery(store, ledger, toolx), store=store)
    return make


def test_submit_then_detail_reaches_done():
    from src.api.app import app
    from src.api.routes.runs import set_kernel_factory
    store, ledger = MemoryStore(), MemoryLedger([])
    set_kernel_factory(_fake_bundle_factory(store, ledger, []))
    try:
        client = TestClient(app)
        r = client.post("/runs", json={"task": "研究量子计算进展"})
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        assert r.json()["status"] == "queued"
        detail = {}
        for _ in range(60):
            detail = client.get(f"/runs/{run_id}").json()
            if detail["status"] in ("done", "failed"):
                break
            time.sleep(0.05)
        assert detail["status"] == "done"
        assert detail["final_answer"] == "研究完成"
    finally:
        set_kernel_factory(None)


def test_detail_404_for_unknown_run():
    from src.api.app import app
    from src.api.routes.runs import set_kernel_factory
    set_kernel_factory(_fake_bundle_factory(MemoryStore(), MemoryLedger([]), []))
    try:
        client = TestClient(app)
        assert client.get("/runs/no-such-run").status_code == 404
    finally:
        set_kernel_factory(None)


def test_resolve_route_409_on_non_paused_run():
    from src.api.app import app
    from src.api.routes.runs import set_kernel_factory
    store, ledger = MemoryStore(), MemoryLedger([])
    set_kernel_factory(_fake_bundle_factory(store, ledger, []))
    try:
        client = TestClient(app)
        r = client.post("/runs", json={"task": "快速任务"})
        run_id = r.json()["run_id"]
        for _ in range(60):
            if client.get(f"/runs/{run_id}").json().get("status") in ("done", "failed"):
                break
            time.sleep(0.05)
        r2 = client.post(f"/runs/{run_id}/resolve_attention",
                         json={"verdict": "side_effect_succeeded"})
        assert r2.status_code == 409            # done run 不可裁决
        r3 = client.post(f"/runs/{run_id}/resolve_attention",
                         json={"verdict": "bogus"})
        assert r3.status_code == 422            # 非法裁决值被 pydantic 拒
    finally:
        set_kernel_factory(None)


def test_sse_stream_delivers_events_then_closes():
    from src.api.app import app
    from src.api.routes.runs import set_kernel_factory
    store, ledger = MemoryStore(), MemoryLedger([])
    set_kernel_factory(_fake_bundle_factory(store, ledger, []))
    try:
        client = TestClient(app)
        r = client.post("/runs", json={"task": "SSE 任务"})
        run_id = r.json()["run_id"]
        for _ in range(60):
            if client.get(f"/runs/{run_id}").json().get("status") == "done":
                break
            time.sleep(0.05)
        resp = client.get(f"/runs/{run_id}/events", params={"timeout_s": 2})
        body = resp.text
        assert resp.status_code == 200
        assert "event: start" in body
        assert "event: done" in body            # 终态事件后流自然关闭
        assert "id: 1" in body                  # Last-Event-ID 协议字段
    finally:
        set_kernel_factory(None)
