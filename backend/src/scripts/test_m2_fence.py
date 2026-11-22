"""M2 块⑤验收：租约 CAS + fencing 僵尸 writer 拦截（真 PG 集成测试）。"""
import asyncio
import sys

import pytest

from src.agent.status import RunStatus
from src.agent.types import Event, EventType, RunConfig
from src.db.connection import get_async_conn
from src.runs.store import FenceLost, PostgresRunStore

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _run(coro):
    return asyncio.run(coro)


async def _new_store():
    conn = await get_async_conn()
    return conn, PostgresRunStore(conn)


async def _cleanup(conn, run_id):
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM agent_runs WHERE id = %s", (run_id,))
    await conn.commit()


async def _expire_lease(conn, run_id):
    """把租约拨到过去，模拟 worker 挂死、租约超时。"""
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE agent_runs SET lease_expires_at = now() - interval '1s' "
            "WHERE id = %s", (run_id,))
    await conn.commit()


def test_claim_lease_cas_and_token_monotonic():
    async def body():
        conn, s1 = await _new_store()
        try:
            run_id = await s1.create_run("t", RunConfig(), "tester")
            # 空闲 → w1 抢到，token=1
            t1 = await s1.claim_lease(run_id, "w1", ttl_s=60)
            assert t1 == 1
            # w1 持有中 → w2 抢不到
            t2 = await s2_claim(conn, run_id, "w2")
            assert t2 is None
            # 同 worker 续租 → 成功，token 递增（bump-always）
            t1b = await s1.claim_lease(run_id, "w1", ttl_s=60)
            assert t1b == 2
            # 租约过期 → w2 可抢，token 继续递增
            await _expire_lease(conn, run_id)
            t2b = await s2_claim(conn, run_id, "w2")
            assert t2b == 3
            # 终态 run 不可抢
            from src.agent.status import RunStatus
            await s1.unbind(run_id)
            await s1.transition_terminal(run_id, RunStatus.CANCELLED, "E_TEST")
            await _expire_lease(conn, run_id)
            assert await s2_claim(conn, run_id, "w2") is None
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


async def s2_claim(conn, run_id, worker_id):
    """第二个 worker：独立连接 + 独立 store 实例（模拟另一台机器）。"""
    s2 = PostgresRunStore(conn)
    return await s2.claim_lease(run_id, worker_id, ttl_s=60)


def test_zombie_writer_blocked_after_lease_loss():
    """★ 核心：w1 失去租约后（token 过期），其写路径全部被拒；新持有者写路径畅通。"""
    async def body():
        conn, s1 = await _new_store()
        try:
            run_id = await s1.create_run("t", RunConfig(), "tester")
            await s1.claim_lease(run_id, "w1", ttl_s=60)
            assert s1._fences[run_id] == 1

            # w1 持有期间写路径畅通（顺带刷新心跳）
            await s1.append_events(run_id, [Event(type=EventType.START,
                                                  run_id=run_id, seq=0)])
            assert s1._fences[run_id] == 1

            # w1 挂死 → 租约过期 → w2 接管（token=2）
            await _expire_lease(conn, run_id)
            s2 = PostgresRunStore(conn)
            t2 = await s2.claim_lease(run_id, "w2", ttl_s=60)
            assert t2 == 2

            # ★ 僵尸 writer：w1 用旧 token 写 → FenceLost
            with pytest.raises(FenceLost):
                await s1.append_events(run_id, [Event(type=EventType.ROUND_START,
                                                      run_id=run_id, seq=0)])
            with pytest.raises(FenceLost):
                await s1.save_run_meta(run_id, final_answer="僵尸写入")
            with pytest.raises(FenceLost):
                await s1.transition_terminal(run_id, RunStatus.DONE)

            # ★ 新持有者写路径畅通，僵尸的写入没有污染事件流
            await s2.append_events(run_id, [Event(type=EventType.ROUND_START,
                                                  run_id=run_id, seq=0)])
            async with conn.cursor() as cur:
                await cur.execute("SELECT seq, type FROM agent_events "
                                  "WHERE run_id = %s ORDER BY seq", (run_id,))
                rows = await cur.fetchall()
            types = [r[1] for r in rows]
            assert "start" in types and "round_start" in types
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_unbound_store_writes_freely():
    """未绑定 fence 的 store（如 supervisor/admin）写路径不受影响——向后兼容。"""
    async def body():
        conn, s = await _new_store()
        try:
            run_id = await s.create_run("t", RunConfig(), "tester")
            # 有人持有租约也没关系：本实例从未绑定 fence
            await s.claim_lease(run_id, "w1", ttl_s=60)
            s2 = PostgresRunStore(conn)         # 新实例，无绑定
            await s2.append_events(run_id, [Event(type=EventType.START,
                                                  run_id=run_id, seq=0)])
            await _cleanup(conn, run_id)
        finally:
            await conn.close()
    _run(body())


def test_claim_returns_none_for_missing_run():
    async def body():
        conn, s = await _new_store()
        try:
            assert await s.claim_lease("00000000-0000-0000-0000-000000000000",
                                       "w1", ttl_s=60) is None
        finally:
            await conn.close()
    _run(body())
