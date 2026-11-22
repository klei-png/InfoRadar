from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.agent.status import TERMINAL,RunStatus
from src.agent.types import Checkpoint,Event,EventType,RunConfig,RunState,ToolCall,RunStore

TERMINAL_VALUES = [s.value for s in TERMINAL]

_META_COLUMNS = {
    "task", "status", "final_answer", "rounds", "prompt_tokens",
    "completion_tokens", "cost_usd", "error_code", "worker_id",
    "lease_expires_at", "heartbeat_at", "fencing_token", "retry_count",
    "max_retries", "next_retry_at", "started_at", "finished_at",
}

#------------------run meta-info-----------------
class FenceLost(RuntimeError):
    """fencing 校验失败：本 worker 的 token 已过期（租约被他人接管）。
    实现层错误——内核不知道它的存在，由 worker 外壳捕获处理。"""


class PostgresRunStore(RunStore):
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn
        self._fences: dict[str, int] = {}

    def use_fence(self, run_id: str, token: int) -> None:
        self._fences[run_id] = token

    def unbind(self, run_id: str) -> None:
        self._fences.pop(run_id, None)

    async def claim_lease(self, run_id: str, worker_id: str, ttl_s: float) -> int | None:
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """UPDATE agent_runs
                       SET worker_id = %s,
                           lease_expires_at = now() + make_interval(secs => %s),
                           fencing_token = fencing_token + 1,
                           heartbeat_at = now()
                       WHERE id = %s
                         AND status <> ALL(%s)
                         AND (worker_id IS NULL
                              OR lease_expires_at < now()
                              OR worker_id = %s)
                       RETURNING fencing_token""",
                    (worker_id, ttl_s, run_id, TERMINAL_VALUES, worker_id),
                )
                row = await cur.fetchone()
        if row is None:
            return None
        token = int(row[0])
        self.use_fence(run_id, token)
        return token

    async def _touch_fence(self, run_id: str) -> None:
        token = self._fences.get(run_id)
        if token is None:
            return
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE agent_runs SET heartbeat_at = now() "
                "WHERE id = %s AND fencing_token = %s",
                (run_id, token),
            )
            if cur.rowcount == 0:
                raise FenceLost(f"E_FENCE_LOST: run {run_id} 的租约已被他人接管")

    async def create_run(self, task: str, config: RunConfig, owner:str) -> str:
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO agent_runs (task, status, config, owner)"
                    "VALUES (%s,%s,%s,%s) RETURNING id",
                    (task, RunStatus.CREATED.value, Jsonb(config.model_dump()),owner),
                )
                row = await cur.fetchone()
        return str(row[0])

    async def save_run_meta(self, run_id:str, **fields: Any) -> None:
        unknown = set(fields) - _META_COLUMNS
        if unknown:
            raise ValueError(f"非法 meta 字段: {sorted(unknown)}；允许: {sorted(_META_COLUMNS)}")
        if not fields:
            return
        set_clause = ", ".join(f"{c} = %s" for c in fields)
        async with self._conn.transaction():
            await self._touch_fence(run_id)
            async with self._conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE agent_runs SET {set_clause} WHERE id = %s",
                    (*fields.values(), run_id),
                )

    async def transition_terminal(self, run_id: str, status: RunStatus,
                                  error_code: str | None = None) -> bool:
        if status not in TERMINAL:
            raise ValueError(f"{status} 不是终态，终态={TERMINAL_VALUES}")
        async with self._conn.transaction():
            await self._touch_fence(run_id)
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """UPDATE agent_runs
                       SET status = %s,
                           error_code = COALESCE(%s, error_code),
                           finished_at = COALESCE(finished_at, now())
                       WHERE id = %s AND status <> ALL(%s)
                       RETURNING id""",
                    (status.value, error_code, run_id, TERMINAL_VALUES),
                )
                row = await cur.fetchone()
        return row is not None

    #-----------------------events streaming----------------------------

    async def append_events(self, run_id: str, events: list[Event]) -> None:
        if not events:
            return
        async with self._conn.transaction():
            await self._touch_fence(run_id)
            async with self._conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(run_id,))
                await cur.execute(
                    "SELECT COALESCE(MAX(seq),0) FROM agent_events WHERE run_id = %s",
                    (run_id,),
                )
                base = (await cur.fetchone())[0]
                await cur.executemany(
                    "INSERT INTO agent_events (event_id, run_id, seq, type, data) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [
                        (e.event_id, run_id, base + i, e.type.value, Jsonb(e.data))
                        for i, e in enumerate(events, start=1)
                    ],
                )
                for i, e in enumerate(events, start=1):
                    e.seq = base + i

    async def get_event(self, run_id: str, seq: int) -> Event | None:
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT event_id, type, data, created_at FROM agent_events "
                "WHERE run_id = %s AND seq = %s",
                (run_id, seq),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return Event(event_id=str(row["event_id"]), type=EventType(row["type"]),
                     run_id=run_id, seq=seq, data=row["data"], ts=row["created_at"])

    async def get_run_meta(self, run_id: str) -> dict[str, Any] | None:
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, task, status, final_answer, rounds, prompt_tokens, "
                "completion_tokens, cost_usd, error_code, created_at, finished_at "
                "FROM agent_runs WHERE id = %s",
                (run_id,),
            )
            row = await cur.fetchone()
        return dict(row) if row else None

#---------------------message-----------------------------
    async def append_messages(self, run_id: str, msgs: list[dict[str, Any]],
                              checkpoint: bool) -> None:
        if not msgs:
            return
        async with self._conn.transaction():
            await self._touch_fence(run_id)
            async with self._conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (run_id,))
                await cur.execute(
                    "SELECT COALESCE(MAX(seq), 0) FROM agent_messages WHERE run_id = %s",
                    (run_id,),
                )
                base = (await cur.fetchone())[0]
                await cur.executemany(
                    "INSERT INTO agent_messages (run_id, seq, role, content, tool_calls, "
                    "tool_call_id, name, checkpoint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (run_id, base + i, m.get("role"), m.get("content"),
                         Jsonb(m["tool_calls"]) if m.get("tool_calls") else None,
                         m.get("tool_call_id"), m.get("name"), checkpoint)
                        for i, m in enumerate(msgs, start=1)
                    ],
                )

#------------------Checkpoint------------------------
    async def save_checkpoint(self, cp: Checkpoint) -> None:
        async with self._conn.transaction():
            await self._touch_fence(cp.run_id)
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO agent_checkpoints (run_id, version, last_event_seq, state)
                                           VALUES (%s, %s, %s, %s)
                                           ON CONFLICT (run_id, version) DO UPDATE
                                           SET last_event_seq = EXCLUDED.last_event_seq,
                                               state = EXCLUDED.state""",
                    (cp.run_id, cp.version, cp.last_event_seq,
                     Jsonb({"state": cp.state.model_dump(mode="json"),
                            "pending_tool_calls": [t.model_dump(mode="json")
                                                   for t in cp.pending_tool_calls]})),
                )

    async def load_checkpoint(self, run_id: str) -> Checkpoint | None:
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT checkpoint_id, version, last_event_seq, state, created_at "
                "FROM agent_checkpoints WHERE run_id = %s "
                "ORDER BY version DESC LIMIT 1",
                (run_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        payload = row["state"]
        return Checkpoint(
            run_id=run_id,
            checkpoint_id=str(row["checkpoint_id"]),
            version=row["version"],
            last_event_seq=row["last_event_seq"],
            state=RunState(**payload["state"]),
            pending_tool_calls=[ToolCall(**t) for t in payload.get("pending_tool_calls", [])],
            created_at=row["created_at"],
        )