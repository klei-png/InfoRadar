import asyncio

import pytest

from src.agent.status import RunStatus
from src.agent.types import (Checkpoint, Event, EventType, Evidence, RunConfig,
                             RunState, ToolCall, Usage)
from src.db.connection import get_async_conn
from src.runs.store import PostgresRunStore

import asyncio
import sys

if sys.platform == "win32":
    # psycopg 异步模式不支持 Windows 默认的 ProactorEventLoop，换 Selector
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def _run(coro):
    return asyncio.run(coro)


async def _new_store():
    conn = await get_async_conn()
    return conn, PostgresRunStore(conn)


async def _cleanup(conn, run_id):
    async with conn.cursor() as cur:   # 级联删 events/messages/checkpoints
        await cur.execute("DELETE FROM agent_runs WHERE id = %s", (run_id,))
    await conn.commit()


def test_create_and_terminal_race():
    async def body():
        conn, store = await _new_store()
        try:
            run_id = await store.create_run("测试任务", RunConfig(), "tester")
            assert len(run_id) == 36                       # uuid
            ok1 = await store.transition_terminal(run_id, RunStatus.CANCELLED, "E_TEST")
            ok2 = await store.transition_terminal(run_id, RunStatus.TIMEOUT)   # 被抢先
            assert ok1 is True and ok2 is False
            async with conn.cursor() as cur:
                await cur.execute("SELECT status, error_code FROM agent_runs WHERE id=%s",
                                  (run_id,))
                status, err = (await cur.fetchone())
            assert status == "cancelled" and err == "E_TEST"   # 后到的 error_code 不覆盖
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_transition_rejects_non_terminal():
    async def body():
        conn, store = await _new_store()
        try:
            run_id = await store.create_run("t", RunConfig(), "tester")
            with pytest.raises(ValueError):
                await store.transition_terminal(run_id, RunStatus.RUNNING)
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_event_seq_monotonic_and_get():
    async def body():
        conn, store = await _new_store()
        try:
            run_id = await store.create_run("t", RunConfig(), "tester")
            evs1 = [Event(type=EventType.START, run_id=run_id, seq=0),
                    Event(type=EventType.ROUND_START, run_id=run_id, seq=0),
                    Event(type=EventType.TOKEN, run_id=run_id, seq=0)]
            await store.append_events(run_id, evs1)
            assert [e.seq for e in evs1] == [1, 2, 3]      # 分配 1..3，传入 seq=0 被覆盖
            evs2 = [Event(type=EventType.DONE, run_id=run_id, seq=0)]
            await store.append_events(run_id, evs2)
            assert evs2[0].seq == 4                        # 跨批次续号
            got = await store.get_event(run_id, 3)
            assert got is not None and got.type == EventType.TOKEN and got.ts.tzinfo
            assert await store.get_event(run_id, 99) is None
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_checkpoint_roundtrip_latest_version():
    async def body():
        conn, store = await _new_store()
        try:
            run_id = await store.create_run("t", RunConfig(), "tester")
            state = RunState(run_id=run_id, rounds=2,
                             usage=Usage(prompt_tokens=100, completion_tokens=50),
                             evidence=[Evidence(evidence_id="EV-1", source="web",
                                                url="https://a", summary="s",
                                                content_ref=f"event:{run_id}:1")])
            cp1 = Checkpoint(run_id=run_id, version=1, last_event_seq=3, state=state)
            cp2 = Checkpoint(run_id=run_id, version=2, last_event_seq=7, state=state,
                             pending_tool_calls=[ToolCall(call_id="c9", name="kb_search",
                                                          arguments={"query": "x"})])
            await store.save_checkpoint(cp1)
            await store.save_checkpoint(cp2)
            loaded = await store.load_checkpoint(run_id)
            assert loaded.version == 2                          # 取最大 version
            assert loaded.last_event_seq == 7
            assert loaded.pending_tool_calls[0].call_id == "c9"  # 恢复保留原 call_id
            assert loaded.state.evidence[0].content_ref == f"event:{run_id}:1"
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_append_messages_seq_and_flag():
    async def body():
        conn, store = await _new_store()
        try:
            run_id = await store.create_run("t", RunConfig(), "tester")
            await store.append_messages(run_id, [{"role": "user", "content": "hi"}], False)
            await store.append_messages(run_id, [{"role": "assistant", "content": "hello"},
                                                 {"role": "user", "content": "again"}], True)
            async with conn.cursor() as cur:
                await cur.execute("SELECT seq, checkpoint FROM agent_messages "
                                  "WHERE run_id=%s ORDER BY seq", (run_id,))
                rows = await cur.fetchall()
            assert [r[0] for r in rows] == [1, 2, 3]            # 跨批次连续
            assert rows[2][1] is True                            # 最后一批带 checkpoint 标记
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())
