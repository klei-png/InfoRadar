"""M2 块②验收：登记幂等 / 两级状态机重试语义 / CAS 守卫 / unknown 联动 / 查询。"""
import asyncio

import pytest

from src.agent.types import RunConfig
from src.db.connection import get_async_conn
from src.runs.ledger import PostgresExecutionLedger
from src.runs.store import PostgresRunStore

if __import__("sys").platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _run(coro):
    return asyncio.run(coro)


async def _setup():
    """每个测试独立连接 + 一个真实 run（FK 需要）。"""
    conn = await get_async_conn()
    store = PostgresRunStore(conn)
    run_id = await store.create_run("ledger-test", RunConfig(), "tester")
    return conn, PostgresExecutionLedger(conn), run_id


async def _cleanup(conn, run_id):
    async with conn.cursor() as cur:   # 级联删 executions/attempts
        await cur.execute("DELETE FROM agent_runs WHERE id = %s", (run_id,))
    await conn.commit()


def test_create_execution_idempotent():
    async def body():
        conn, ledger, run_id = await _setup()
        try:
            id1 = await ledger.create_execution(run_id, "send_email", "k1", "d1")
            id2 = await ledger.create_execution(run_id, "send_email", "k1", "d1")
            assert id1 == id2                     # 幂等：同 idem_key 复用同一记录
            rec = await ledger.get_execution(run_id, "k1")
            assert rec["status"] == "pending"     # 已登记、无尝试在途
            assert rec["attempts"] == []
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_attempt_lifecycle_and_retry_semantics():
    async def body():
        conn, ledger, run_id = await _setup()
        try:
            eid = await ledger.create_execution(run_id, "send_email", "k2", "d2")
            a1 = await ledger.start_attempt(eid)
            rec = await ledger.get_execution(run_id, "k2")
            assert rec["status"] == "executing" and rec["attempts"][0]["attempt_no"] == 1
            await ledger.finish_attempt(a1, ok=False, result_digest=None,
                                        error_code="E_TOOL_FAILED")
            rec = await ledger.get_execution(run_id, "k2")
            assert rec["status"] == "executing"               # ★ attempt 失败 ≠ execution 失败
            assert rec["attempts"][0]["status"] == "failed"
            a2 = await ledger.start_attempt(eid)              # 重试 = 新 attempt
            await ledger.finish_attempt(a2, ok=True, result_digest="sha256:ok",
                                        error_code=None)
            await ledger.complete_execution(eid, "succeeded", "sha256:ok")
            rec = await ledger.get_execution(run_id, "k2")
            assert rec["status"] == "succeeded"
            assert [a["attempt_no"] for a in rec["attempts"]] == [1, 2]  # 重试只加 attempt
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_complete_guard_prevents_resurrection():
    async def body():
        conn, ledger, run_id = await _setup()
        try:
            eid = await ledger.create_execution(run_id, "t", "k3", "d")
            await ledger.complete_execution(eid, "failed", None)
            await ledger.complete_execution(eid, "succeeded", "x")   # 已终态，CAS 拒绝
            rec = await ledger.get_execution(run_id, "k3")
            assert rec["status"] == "failed" and rec["result_digest"] is None
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_mark_unknown_cascades_to_running_attempt():
    async def body():
        conn, ledger, run_id = await _setup()
        try:
            eid = await ledger.create_execution(run_id, "t", "k4", "d")
            await ledger.start_attempt(eid)
            await ledger.mark_unknown(eid)
            rec = await ledger.get_execution(run_id, "k4")
            assert rec["status"] == "unknown"                     # execution in-doubt
            assert rec["attempts"][0]["status"] == "unknown"      # 在途尝试一并标
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_get_execution_missing():
    async def body():
        conn, ledger, run_id = await _setup()
        try:
            assert await ledger.get_execution(run_id, "nope") is None
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())
