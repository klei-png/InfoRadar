"""api/routes/runs.py — M3 块②：harness 的最小产品外壳。

POST /runs                                提交任务（202，后台 worker 执行）
GET  /runs/{run_id}                       运行详情（状态/终答/轮数/用量）
GET  /runs/{run_id}/events                SSE 事件流（Last-Event-ID 断点续传）
POST /runs/{run_id}/resolve_attention     人工三裁决（needs_attention → 重启 worker）

内核依赖通过 set_kernel_factory 注入——测试用 fake 全量替换。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.loop import RunExecutor
from src.agent.recovery import Recovery
from src.agent.status import TERMINAL, RunStatus
from src.agent.types import RunConfig, RunStore

router = APIRouter(prefix="/runs", tags=["runs"])

_TERMINAL_VALUES = {s.value for s in TERMINAL}


@dataclass
class KernelBundle:
    """一次注入全部内核组件；worker 与路由共用同一实例（M3 单 worker）。"""
    executor: RunExecutor
    recovery: Recovery
    store: RunStore


_factory = None


def set_kernel_factory(fn) -> None:
    """测试/部署时替换内核组装方式。fn: () -> KernelBundle | coroutine。"""
    global _factory
    _factory = fn


async def _default_factory() -> KernelBundle:
    """生产组装：PG store/ledger + LiteLLM + 默认注册表。惰性 import。"""
    from src.db.connection import get_async_conn
    from src.llm.adapter import LiteLLMAdapter
    from src.agent.tool_executor import ToolExecutor
    from src.agent.policy import Policy
    from src.runs.store import PostgresRunStore
    from src.runs.ledger import PostgresExecutionLedger
    from src.tools.defaults import default_registry
    conn = await get_async_conn()
    store = PostgresRunStore(conn)
    ledger = PostgresExecutionLedger(conn)
    toolx = ToolExecutor(default_registry(), Policy())
    executor = RunExecutor(LiteLLMAdapter(), toolx, store, ledger)
    return KernelBundle(executor=executor,
                        recovery=Recovery(store, ledger, toolx), store=store)


async def _bundle() -> KernelBundle:
    if _factory is None:
        return await _default_factory()
    result = _factory()
    if asyncio.iscoroutine(result):
        result = await result
    return result


#----------worker（M3 内置单 worker，独立进程化是 M4 的事）----------

async def _worker(bundle: KernelBundle, run_id: str, task: str,
                  config: RunConfig) -> None:
    try:
        plan = await bundle.recovery.plan(run_id, config)
        if plan.action == "needs_attention":
            return                      # 挂起等人工裁决；resolve 路由会再次拉起
        if plan.action == "failed":
            # 无存档/漂移：让 executor 走正常失败路径落终态（无 pending 可重放）
            await bundle.executor.execute(run_id, task, config)
            return
        await bundle.executor.execute(run_id, task, config,
                                      state=plan.state, pending=plan.pending)
    except Exception as e:              # worker 不许无声死亡
        print(f"[worker] run {run_id} 异常退出: {e!r}")


#----------------routes----------------

class SubmitIn(BaseModel):
    task: str = Field(min_length=2, max_length=8000)
    model: str | None = None
    max_rounds: int = Field(12, ge=1, le=50)
    token_budget: int | None = Field(None, ge=100)
    wall_timeout: float = Field(300, gt=1, le=1800)
    allowed_tools: list[str] | None = None


@router.post("", status_code=202)
async def submit_run(body: SubmitIn):
    bundle = await _bundle()
    config = RunConfig(model=body.model, max_rounds=body.max_rounds,
                       token_budget=body.token_budget,
                       wall_timeout=body.wall_timeout,
                       allowed_tools=body.allowed_tools)
    run_id = await bundle.store.create_run(body.task, config, owner="api")
    await bundle.store.save_run_meta(run_id, status=RunStatus.QUEUED.value)
    asyncio.get_running_loop().create_task(
        _worker(bundle, run_id, body.task, config))
    return {"run_id": run_id, "status": "queued"}


@router.get("/{run_id}")
async def run_detail(run_id: str):
    bundle = await _bundle()
    meta = await bundle.store.get_run_meta(run_id)
    if meta is None:
        raise HTTPException(404, f"run {run_id} 不存在")
    return meta


@router.get("/{run_id}/events")
async def run_events(run_id: str, last_event_id: int = 0, timeout_s: float = 30):
    """SSE：从 last_event_id+1 逐条补发，run 进终态后关闭。
    断线重连带 Last-Event-ID 即无缝续传——事件流有 UNIQUE(run_id, seq) 兜底。"""
    bundle = await _bundle()
    if await bundle.store.get_run_meta(run_id) is None:
        raise HTTPException(404, f"run {run_id} 不存在")

    async def gen():
        seq = last_event_id
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            ev = await bundle.store.get_event(run_id, seq + 1)
            if ev is not None:
                seq = ev.seq
                payload = json.dumps({"type": ev.type.value, "data": ev.data,
                                      "ts": ev.ts.isoformat()}, ensure_ascii=False)
                yield f"id: {ev.seq}\nevent: {ev.type.value}\ndata: {payload}\n\n"
                if ev.type.value in ("done", "error", "cancelled"):
                    return
            else:
                meta = await bundle.store.get_run_meta(run_id)
                if meta and meta["status"] in _TERMINAL_VALUES:
                    return
                await asyncio.sleep(0.2)

    return StreamingResponse(gen(), media_type="text/event-stream")


class ResolveIn(BaseModel):
    verdict: str = Field(pattern="^(side_effect_succeeded|side_effect_failed|abort)$")


@router.post("/{run_id}/resolve_attention", status_code=202)
async def resolve_attention(run_id: str, body: ResolveIn):
    """三裁决（spec §7）：succeeded / failed → 回灌结果并重启 worker；abort → 终态取消。"""
    bundle = await _bundle()
    meta = await bundle.store.get_run_meta(run_id)
    if meta is None:
        raise HTTPException(404, f"run {run_id} 不存在")
    if meta["status"] != RunStatus.NEEDS_ATTENTION.value:
        raise HTTPException(409, f"run {run_id} 状态为 {meta['status']}，"
                                 "仅 needs_attention 可裁决")
    outcome = await bundle.executor.resolve_attention(run_id, body.verdict)
    if outcome.status == RunStatus.QUEUED:
        # 裁决完成 → 重新拉起 worker（Recovery 会从裁决后的 checkpoint resume）
        cp = await bundle.store.load_checkpoint(run_id)
        config = cp.state.config_snapshot if cp else RunConfig().model_dump()
        asyncio.get_running_loop().create_task(
            _worker(bundle, run_id, meta.get("task") or "",
                    RunConfig(**config)))
    return {"run_id": run_id, "status": outcome.status.value}
