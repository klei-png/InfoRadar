"""M0 第 2 块验收：表存在 + 关键 UNIQUE 约束 + fencing_token 字段。"""
from src.db.connection import get_conn

AGENT_TABLES = ("agent_runs", "agent_messages", "agent_events",
                "agent_checkpoints", "tool_executions", "tool_execution_attempts")


def _fetch(sql: str) -> list:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def test_tables_exist():
    rows = _fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = {r[0] for r in rows}
    for t in AGENT_TABLES:
        assert t in tables, f"缺表: {t}"


def test_fencing_token_column():
    rows = _fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='agent_runs' AND column_name='fencing_token'"
    )
    assert rows, "agent_runs 缺 fencing_token 列"


def test_key_unique_constraints():
    defs = [r[0] for r in _fetch("SELECT indexdef FROM pg_indexes WHERE schemaname='public'")]
    for table, cols in (
        ("agent_events", "(run_id, seq)"),
        ("agent_messages", "(run_id, seq)"),
        ("agent_checkpoints", "(run_id, version)"),
        ("tool_executions", "(run_id, idem_key)"),
        ("tool_execution_attempts", "(execution_id, attempt_no)"),
    ):
        hit = [d for d in defs if f"ON public.{table}" in d and "UNIQUE" in d and cols in d]
        assert hit, f"{table} 缺 UNIQUE {cols}"
