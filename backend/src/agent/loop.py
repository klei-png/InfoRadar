from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass

from src.agent.tool_executor import ToolExecutor
from src.agent.context import ContextManager
from src.agent.types import *
from src.llm.adapter import ModelAdapterError, LiteLLMAdapter
from src.tools.base import ToolResult

EVIDENCE_MIN_CHARS = 200
EVIDENCE_SUMMARY_CHARS = 300

class PersistFailed(Exception):
    """关键事件/消息落库失败"""

@dataclass
class RunOutcome:
    status: RunStatus
    final_answer: str | None = None
    error_code: str | None = None
    rounds: int = 0

class _Events:
    def __init__(self, run_id: str, store) -> None:
        self._run_id = run_id
        self._store = store
        self.last_seq = 0

    async def emit(self, type: EventType, data: dict, critical: bool = True) -> None:
        ev = Event(type=type, run_id=self._run_id, seq=0, data=data)
        try:
            await self._store.append_events(self._run_id, [ev])
            self.last_seq = max(self.last_seq, ev.seq)
        except PersistFailed:
            raise
        except Exception as e:
            if critical:
                raise PersistFailed(f"关键事件 {type.value} 落库失败: {e}") from e

class RunExecutor:
    def __init__(self, adapter: LiteLLMAdapter, toolx: ToolExecutor, store: RunStore,
                 ledger: ExecutionLedger,
                 ctx_mgr: "ContextManager | None" = None) -> None:
        self._adapter = adapter
        self._toolx = toolx
        self._store = store
        self._ledger = ledger
        self._ctx = ctx_mgr or ContextManager()

    async def execute(self, run_id: str, task: str, config: RunConfig,
                      state: RunState | None = None,
                      pending: list[ToolCall] | None = None) -> RunOutcome:
        if state is None:
            state = RunState(run_id=run_id, config_snapshot=config.model_dump(),
                             messages=[{"role": "user", "content": task}])
        ctx = RunContext(run_id=run_id, state=state, store=self._store)
        ev = _Events(run_id, self._store)
        schemas = self._toolx.schemas(config.allowed_tools)
        in_flight: dict = {}        #state tracker to prevent duplicate calls

        try:
            await ev.emit(EventType.START, {"task": task})
            async with asyncio.timeout(config.wall_timeout):
                return await self._loop(run_id, config, state, ctx, ev, schemas,
                                        in_flight, pending)
        except TimeoutError:
            return await self._on_wall_timeout(run_id, state, ev, in_flight)
        except PersistFailed as e:
            return await self._on_persist_failed(run_id, e, state)
        except ModelAdapterError as e:
            return await self._on_model_error(run_id, state, ev, e)

    #--------------------main loop---------------------------
    async def _loop(self,run_id: str, config: RunConfig, state: RunState,
                    ctx: RunContext, ev: _Events, schemas: list[dict],
                    in_flight: dict, pending: list[ToolCall] | None = None) -> RunOutcome:
        version = 0
        seen_calls: dict[str, int] = {}   # 死循环检测：签名(name+args) → 出现次数
        if pending:
            # 崩溃恢复：先重放 checkpoint 里未完成的工具调用（spec §2.4 决策树）
            await self._drain_pending(run_id, pending, state, ctx, ev, in_flight)
        for round_no in range(1, config.max_rounds + 1):
            used = state.usage.prompt_tokens + state.usage.completion_tokens
            if config.token_budget is not None and used > config.token_budget:
                return await self._fail(run_id, ev, "E_BUDGET_EXCEEDED",
                                        f"token 预算耗尽: {used}>{config.token_budget}",
                                        state.rounds)
            await ev.emit(EventType.ROUND_START, {"round": round_no})
            state.rounds = round_no

            # 上下文压缩（M3）：接近预算时压缩旧轮 tool 结果，压缩后立即存档
            comp = self._ctx.compact(state)
            if comp is not None:
                await ev.emit(EventType.CONTEXT_COMPACTED, {
                    "rounds_total": comp.rounds_total, "rounds_kept": comp.rounds_kept,
                    "compressed_msgs": comp.compressed_msgs,
                    "chars_before": comp.chars_before, "chars_after": comp.chars_after})
                version += 1
                await self._checkpoint(run_id, state, ev, version)

            resp = await self._adapter.complete(state.messages, tools=schemas or None,
                config=ModelConfig(model=config.model))
            state.usage.add(resp.usage)
            state.model_version = resp.model_version
            await ev.emit(EventType.USAGE, {"usage": state.usage.model_dump()},
                          critical=False)

            #----------------- final answer branch ----------------
            if not resp.tool_calls:
                state.messages.append({"role": "assistant", "content": resp.content or ""})
                await self._append_msgs(run_id, state.messages[-1:], round_no)
                await ev.emit(EventType.DONE,{"final_answer": resp.content, "rounds": round_no})
                if not await self._store.transition_terminal(run_id, RunStatus.DONE):
                    return RunOutcome(RunStatus.FAILED, error_code="E_TERMINAL_RACE_LOST", rounds=state.rounds)
                try:
                    await self._store.save_run_meta(
                        run_id, final_answer=resp.content, rounds=state.rounds,
                        prompt_tokens=state.usage.prompt_tokens,
                        completion_tokens=state.usage.completion_tokens,
                        cost_usd=state.usage.cost_usd)
                except Exception:
                    pass
                return RunOutcome(RunStatus.DONE, final_answer=resp.content,rounds=state.rounds)

            state.messages.append({
                "role": "assistant",
                "content": resp.content or "",
                "tool_calls": [
                    {"id": tc.call_id, "type": "function",
                     "function": {"name": tc.name,"arguments": json.dumps(tc.arguments,ensure_ascii=False)}}
                        for tc in resp.tool_calls]
                })
            await self._append_msgs(run_id, state.messages[-1:], round_no)

            # write-ahead 存档：执行副作用前先冻结"待办"现场（崩溃后据此重放/裁决）
            side_calls = [tc for tc in resp.tool_calls
                          if (t := self._toolx.precheck(tc.name)) is not None
                          and t.defn.side_effect]
            if side_calls:
                version += 1
                await self._checkpoint(run_id, state, ev, version, pending=side_calls)

            tool_msgs: list[dict] = []
            for tc in resp.tool_calls:
                tool = self._toolx.precheck(tc.name)
                if tool is None:
                    await ev.emit(EventType.TOOL_DENIED,
                                  {"call_id": tc.call_id, "tool": tc.name,
                                   "reason": "未注册或被策略拒绝"})
                    tool_msgs.append({"role": "tool", "tool_call_id": tc.call_id,
                                      "content": f"工具 {tc.name} 被策略拒绝，请改用其他方式"})
                    continue
                # 死循环检测：同签名第 3 次出现 → fatal（spec 9.1；重放不计入）
                sig = hashlib.sha256(
                    (tc.name + json.dumps(tc.arguments, sort_keys=True)).encode()
                ).hexdigest()
                seen_calls[sig] = seen_calls.get(sig, 0) + 1
                if seen_calls[sig] >= 3:
                    return await self._fail(run_id, ev, "E_LOOP_DETECTED",
                                            f"同签名调用 {seen_calls[sig]} 次，疑似死循环",
                                            state.rounds)

                await ev.emit(EventType.TOOL_CALL, {"call_id": tc.call_id,
                                                    "tool": tc.name,
                                                    "arguments": tc.arguments})
                if tool.defn.side_effect:
                    r = await self._run_with_ledger(run_id, tc, ctx, ev, in_flight)
                else:
                    r = await self._run_tool(tc, ctx, ev)
                tool_msgs.append({"role": "tool", "tool_call_id": tc.call_id,
                                  "content": r.content})
                if (r.ok and not tool.defn.side_effect
                        and len(r.content) >= EVIDENCE_MIN_CHARS):
                    state.evidence.append(Evidence(
                        evidence_id=f"EV-{len(state.evidence) + 1}", source=tc.name,
                        summary=r.content[:EVIDENCE_SUMMARY_CHARS],
                        content_ref=f"event:{run_id}:{ev.last_seq}"))
            state.messages.extend(tool_msgs)
            await self._append_msgs(run_id, tool_msgs, round_no)
            await ev.emit(EventType.ROUND_END, {"round": round_no})

            version += 1
            await self._checkpoint(run_id, state, ev, version)

        return await self._fail(run_id, ev, "E_MAX_ROUNDS",
                                    f"{config.max_rounds} 轮内未得到终答", state.rounds)

    async def _drain_pending(self, run_id: str, pending: list[ToolCall],
                             state: RunState, ctx: RunContext, ev: _Events,
                             in_flight: dict) -> None:
        """重放崩溃前未完成的工具调用：补 assistant 消息 + 逐个执行 + 回灌。"""
        await ev.emit(EventType.RETRY, {"replayed_tool_calls": len(pending)})
        state.messages.append({"role": "assistant", "content": "",
                               "tool_calls": [{"id": tc.call_id, "type": "function",
                                               "function": {"name": tc.name,
                                                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                                              for tc in pending]})
        await self._append_msgs(run_id, state.messages[-1:], 0)
        tool_msgs: list[dict] = []
        for tc in pending:
            tool = self._toolx.precheck(tc.name)
            if tool is None:
                await ev.emit(EventType.TOOL_DENIED,
                              {"call_id": tc.call_id, "tool": tc.name,
                               "reason": "恢复时工具不可用"})
                tool_msgs.append({"role": "tool", "tool_call_id": tc.call_id,
                                  "content": f"工具 {tc.name} 不可用，请改用其他方式"})
                continue
            await ev.emit(EventType.TOOL_CALL, {"call_id": tc.call_id,
                                                "tool": tc.name,
                                                "arguments": tc.arguments})
            if tool.defn.side_effect:
                r = await self._run_with_ledger(run_id, tc, ctx, ev, in_flight)
            else:
                r = await self._run_tool(tc, ctx, ev)
            tool_msgs.append({"role": "tool", "tool_call_id": tc.call_id,
                              "content": r.content})
            if (r.ok and not tool.defn.side_effect
                    and len(r.content) >= EVIDENCE_MIN_CHARS):
                state.evidence.append(Evidence(
                    evidence_id=f"EV-{len(state.evidence) + 1}", source=tc.name,
                    summary=r.content[:EVIDENCE_SUMMARY_CHARS],
                    content_ref=f"event:{run_id}:{ev.last_seq}"))
        state.messages.extend(tool_msgs)
        await self._append_msgs(run_id, tool_msgs, 0)

    # ---------------- Tool Execution -----------------
    async def _run_tool(self, tc: ToolCall, ctx: RunContext, ev: _Events) -> ToolResult:
        r = await self._toolx.execute(tc, ctx)
        await ev.emit(EventType.TOOL_RESULT,
                      {"call_id": tc.call_id, "tool": tc.name, "ok": r.ok,
                       "error_code": r.error_code, "content": r.content})  # 全文进事件
        return r

    async def _run_with_ledger(self, run_id: str, tc: ToolCall, ctx: RunContext,
                               ev: _Events, in_flight: dict) -> ToolResult:
        """副作用工具：write-ahead → 执行 → 回填。spec §4：事实来源是 Ledger。"""
        idem_key = hashlib.sha256(f"{run_id}{tc.call_id}".encode()).hexdigest()
        eid = await self._ledger.create_execution(
            run_id, tc.name, idem_key,
            args_digest=hashlib.sha256(
                json.dumps(tc.arguments, sort_keys=True).encode()).hexdigest())
        aid = await self._ledger.start_attempt(eid)
        in_flight.update(execution_id=eid, tool=tc.name)
        r = await self._toolx.execute(tc, ctx)
        in_flight.clear()
        digest = hashlib.sha256(r.content.encode()).hexdigest()
        if r.ok:
            await self._ledger.finish_attempt(aid, True, digest, None)
            await self._ledger.complete_execution(eid, "succeeded", digest)
        else:
            await self._ledger.finish_attempt(aid, False, None, r.error_code)
            await self._ledger.complete_execution(eid, "failed", None)
        await ev.emit(EventType.TOOL_RESULT,
                      {"call_id": tc.call_id, "tool": tc.name, "ok": r.ok,
                       "error_code": r.error_code, "content": r.content})
        return r

    #----------------- exceptions and cleanup path ---------------------
    async def _on_wall_timeout(self, run_id: str, state: RunState, ev: _Events,
                               in_flight: dict) -> RunOutcome:
        if in_flight.get("execution_id"):
            await self._ledger.mark_unknown(in_flight["execution_id"])
            await ev.emit(EventType.ATTENTION_REQUIRED,
                          {"tool": in_flight["tool"],
                           "execution_id": in_flight["execution_id"],
                           "reason": "wall_timeout 期间副作用在途，结果不可确认"})
            await self._store.save_run_meta(run_id,
                                            status=RunStatus.NEEDS_ATTENTION.value)
            return RunOutcome(RunStatus.NEEDS_ATTENTION,
                              error_code="E_UNKNOWN_SIDE_EFFECT", rounds=state.rounds)
        await ev.emit(EventType.ERROR, {"error_code": "E_RUN_TIMEOUT"})
        await self._store.transition_terminal(run_id, RunStatus.TIMEOUT, "E_RUN_TIMEOUT")
        return RunOutcome(RunStatus.TIMEOUT, error_code="E_RUN_TIMEOUT",
                          rounds=state.rounds)

    async def _on_persist_failed(self, run_id: str, e: PersistFailed,
                                 state: RunState) -> RunOutcome:
        try:
            await self._store.save_run_meta(run_id, worker_id=None, lease_expires_at=None)
        except Exception:
            pass
        return RunOutcome(RunStatus.RUNNING, error_code="E_PERSIST_FAILED",
                          rounds=state.rounds)

    async def _on_model_error(self, run_id: str, state: RunState, ev: _Events,
                              e: ModelAdapterError) -> RunOutcome:
        await ev.emit(EventType.ERROR, {"error_code": "E_MODEL_UNAVAILABLE",
                                        "message": str(e)})
        await self._store.transition_terminal(run_id, RunStatus.FAILED,
                                              "E_MODEL_UNAVAILABLE")
        return RunOutcome(RunStatus.FAILED, error_code="E_MODEL_UNAVAILABLE",
                          rounds=state.rounds)

    async def _fail(self, run_id: str, ev: _Events, code: str, msg: str,
                    rounds: int) -> RunOutcome:
        await ev.emit(EventType.ERROR, {"error_code": code, "message": msg})
        await self._store.transition_terminal(run_id, RunStatus.FAILED, code)
        return RunOutcome(RunStatus.FAILED, error_code=code, rounds=rounds)

    #-------------------persistence helper----------------------
    async def _append_msgs(self, run_id: str, msgs: list[dict], round_no: int) -> None:
        try:
            await self._store.append_messages(run_id, msgs, checkpoint=False)
        except Exception as e:
            raise PersistFailed(f"round{round_no} 消息落库失败: {e}") from e

    async def _checkpoint(self, run_id: str, state: RunState, ev: _Events,
                          version: int,
                          pending: list[ToolCall] | None = None) -> None:
        cp = Checkpoint(run_id=run_id, version=version, last_event_seq=ev.last_seq,
                        state=state.model_copy(deep=True),
                        pending_tool_calls=list(pending or []))
        await self._store.save_checkpoint(cp)
        await ev.emit(EventType.CHECKPOINT, {"version": version}, critical=False)