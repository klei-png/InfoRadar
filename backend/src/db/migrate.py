from __future__ import annotations

import pathlib

from src.db.connection import get_conn

# backend/src/db/migrate.py → 向上三级到仓库根，再进 docs/migrations
MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[3] / "docs" / "migrations"


def main() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
            )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations")
            applied = {v for (v,) in cur.fetchall()}

        for f in sorted(MIGRATIONS_DIR.glob("V*.sql")):
            version = int(f.stem[1:])
            if version in applied:
                print(f"skip V{version} (already applied)")
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(f.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                    )
                conn.commit()
                print(f"applied V{version}: {f.name}")
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
