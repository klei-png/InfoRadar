from __future__ import annotations

from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

class PostgresExecutionLedger:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def create_execution(self, run_id: str, tool_name: str, idem_key: str,
                               args_digest: str) -> int:
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO tool_executions (run_id, tool_name, idem_key,
                                                  args_digest, status)
                       VALUES (%s, %s, %s, %s, 'pending')
                       ON CONFLICT (run_id, idem_key) DO UPDATE
                       SET updated_at = now()
                       RETURNING id""",
                    (run_id, tool_name, idem_key, args_digest),
                )
                row = await cur.fetchone()
            return row[0]

    async def start_attempt(self, execution_id: int) -> int:
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_xact_lock(%s::bigint)", (execution_id,))
                await cur.execute(
                    "SELECT COALESCE(MAX(attempt_no), 0) FROM tool_execution_attempts "
                    "WHERE execution_id = %s",
                    (execution_id,),
                )
                next_no = (await cur.fetchone())[0] + 1
                await cur.execute(
                    "UPDATE tool_executions SET status = 'executing', updated_at = now() "
                    "WHERE id = %s AND status IN ('pending', 'executing')",
                    (execution_id,),
                )
                await cur.execute(
                    "INSERT INTO tool_execution_attempts (execution_id, attempt_no, status) "
                    "VALUES (%s, %s, 'running') RETURNING id",
                    (execution_id, next_no),
                )
                row = await cur.fetchone()
        return row[0]

    async def finish_attempt(self, attempt_id: int, ok: bool,
                             result_digest: str | None, error_code: str | None) -> None:
        status = "succeeded" if ok else "failed"
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """UPDATE tool_execution_attempts
                       SET status = %s, finished_at = now(),
                           result_digest = %s, error_code = %s
                       WHERE id = %s AND status = 'running'""",
                    (status, result_digest, error_code, attempt_id),
                )

    async def complete_execution(self, execution_id: int,
                            status: Literal["succeeded", "failed", "unknown"],
                            result_digest: str | None) -> None:
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """UPDATE tool_executions
                       SET status = %s, result_digest = COALESCE(%s, result_digest),
                           updated_at = now()
                       WHERE id = %s AND status IN ('pending', 'executing')""",
                    (status, result_digest, execution_id),
                )

    async def mark_unknown(self, execution_id: int) -> None:
        async with self._conn.transaction():
            async with self._conn.cursor() as cur:
                await cur.execute(
                    "UPDATE tool_execution_attempts SET status = 'unknown', "
                    "finished_at = now() WHERE execution_id = %s AND status = 'running'",
                    (execution_id,),
                )
                await cur.execute(
                    """UPDATE tool_executions SET status = 'unknown', updated_at = now()
                       WHERE id = %s AND status IN ('pending', 'executing')""",
                    (execution_id,),
                )

    async def get_execution(self, run_id: str, idem_key: str) -> dict[str, Any] | None:
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, run_id, tool_name, idem_key, args_digest, status, "
                "result_digest, error_code FROM tool_executions "
                "WHERE run_id = %s AND idem_key = %s",
                (run_id, idem_key),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            await cur.execute(
                "SELECT id, attempt_no, status, result_digest, error_code, "
                "started_at, finished_at FROM tool_execution_attempts "
                "WHERE execution_id = %s ORDER BY attempt_no",
                (row["id"],),
            )
            row["attempts"] = await cur.fetchall()
        return dict(row)