import json
import logging
from datetime import datetime, timezone
from typing import Iterable
import psycopg

from src.models.schema import Item
from src.pipeline.dedup import url_hash as gen_url_hash, simhash64

logger = logging.getLogger(__name__)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return
    return value.replace("\x00", "")


def insert_items(conn: psycopg.Connection, items: Iterable[Item]) -> int:
    sql = """
         INSERT INTO items (
            source_id, external_id, url, url_hash, title, title_simhash,
            content, snippet, published_at, fetched_at, category, lang, raw_meta
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) ON CONFLICT DO NOTHING  
    """
    inserted = 0
    with conn.cursor() as cursor:
        for it in items:
            uh = gen_url_hash(it.url)
            th = simhash64(it.title) if it.title else 0
            if th >= 2 ** 63:
                th -= 2 ** 64
            fetch_time = it.fetched_at or datetime.now(timezone.utc)
            try:
                cursor.execute(sql, (
                    it.source_id, it.external_id, _clean_text(it.url), uh,
                    _clean_text(it.title)[:512] if it.title else "",
                    th, _clean_text(it.content), _clean_text(it.snippet),
                    it.published_at, fetch_time,
                    it.category, it.lang,
                    json.dumps(it.raw_meta, ensure_ascii=False)
                ))
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                logger.error(f"Failed to insert item {it.url}: {e}")
                conn.rollback()
        conn.commit()
        return inserted


def fetch_candidates_for_agent(conn: psycopg.Connection, limit: int = 80) -> list[dict]:
    sql = """
            SELECT id, source_id, title, snippet, url, category, published_at
            FROM items
            WHERE status = 'new' 
              AND fetched_at >= NOW() - INTERVAL '24 hours'
            ORDER BY published_at DESC
            LIMIT %s
        """
    with conn.cursor() as cursor:
        cursor.execute(sql, (limit,))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def fetch_items_by_ids(conn: psycopg.Connection, ids) -> list[dict]:
    sql = """
        SELECT id,source_id,title,snippet,url,category,published_at
        FROM items
        WHERE id=ANY(%s)
    """
    with conn.cursor() as cursor:
        cursor.execute(sql,(ids,))
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns,row)) for row in cursor.fetchall()]

def record_feedback(conn: psycopg.Connection, item_id: int | None = None,
                    digest_id: int | None = None, rating: int = 0,
                    comment: str | None = None,
                    prompt_version: str | None = None):
    sql = """
        INSERT INTO feedback (item_id, digest_id, rating, comment, prompt_version)
        VALUES (%s, %s, %s, %s, %s)
    """
    if rating not in (1, 0, -1):
        raise ValueError(f"rating must be 1/0/-1, got {rating}")
    with conn.cursor() as cursor:
        cursor.execute(sql, (item_id, digest_id, rating, comment, prompt_version))
    conn.commit()


def get_recent_feedback(conn: psycopg.Connection, limit: int = 10) -> list[dict]:
    sql = """
        SELECT i.title, i.snippet, f.rating, f.created_at
        FROM feedback f
        JOIN items i ON i.id = f.item_id
        WHERE f.rating IN (1, -1)
        ORDER BY f.created_at DESC
        LIMIT %s
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (limit,))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def save_scores(conn: psycopg.Connection, results: list[dict]) -> int:
    """
        batch write score results and flip item statuses
        result format: [{item_id,model_score,reason}]
    """
    upsert = """
        INSERT  INTO item_scores (item_id, model_score, reason)
        VALUES (%s, %s, %s)
        ON CONFLICT (item_id) DO UPDATE
        SET model_score = EXCLUDED.model_score, reason = EXCLUDED.reason
    """
    flip = "UPDATE items SET status = 'scored' WHERE id = %s"
    n = 0
    with conn.cursor() as cursor:
        for r in results:
            cursor.execute(upsert, (r["item_id"], r["model_score"], r["reason"][:255]))
            cursor.execute(flip, (r["item_id"],))
            n += 1
    conn.commit()
    return n


def fetch_top_item(conn: psycopg.Connection, min_score: int = 7, hours: int = 24, limit: int = 200) -> list[dict]:
    """ get the high-scoring items within the time window for the summary agent to use.
        items without published_at are excluded: digest is grouped by publish day."""
    sql = """
        SELECT i.id,i.category,i.title,i.snippet,i.url,i.published_at,
                s.model_score,s.reason
        FROM items i
        JOIN item_scores s ON s.item_id = i.id
        WHERE s.model_score >= %s
            AND i.fetched_at >= NOW() - make_interval(hours => %s)
            AND i.published_at IS NOT NULL
        ORDER BY i.published_at DESC
        LIMIT %s
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (min_score, hours, limit))
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def save_digest(conn: psycopg.Connection, date, category: str,
                content_md: str, item_count: int, cost_tokens: int,
                prompt_version: str):
    sql = """
        INSERT INTO digests (date, category, content_md,item_count,
                            cost_tokens, prompt_version, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (date,category) DO UPDATE SET
            content_md = EXCLUDED.content_md,
            item_count = EXCLUDED.item_count,
            cost_tokens = EXCLUDED.cost_tokens,
            prompt_version = EXCLUDED.prompt_version,
            generated_at = NOW()
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (date, category, content_md, item_count,
                             cost_tokens, prompt_version))
    conn.commit()


def mark_items_status(conn: psycopg.Connection, item_ids: list[int], status: str):
    sql = """
        UPDATE items SET status = %s WHERE id = ANY(%s)
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (status, item_ids))
    conn.commit()


def list_recent_digests(conn: psycopg.Connection, days: int = 7) -> list[dict]:
    # 按「生成时间」过滤：digest 按文章发布日分组，历史文章生成的简报也应可见
    sql = """
        SELECT date,category,item_count,cost_tokens,prompt_version,
            generated_at,LEFT(content_md,120) AS preview
        FROM digests
        WHERE generated_at >= NOW() - (%s || ' days')::interval
        ORDER BY date DESC, category
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (str(days),))
        res = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
        return res


def get_latest_digest(conn: psycopg.Connection, category: str, on_date=None) -> dict | None:
    # 按天分组后每篇 category 都是 'all'，需支持按 date 精确定位全文
    sql = """
        SELECT date, category, content_md, item_count, generated_at
        FROM digests WHERE category = %s
    """
    params = [category]
    if on_date is not None:
        sql += " AND date = %s"
        params.append(on_date)
    sql += " ORDER BY date DESC LIMIT 1"
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            return None
        return dict(zip([d[0] for d in cursor.description], row))

def list_scored_items(conn: psycopg.Connection,category: str|None = None,
                      min_score: int = 0, limit: int = 50, offset: int = 0) -> list[dict]:
    sql = """
        SELECT i.id,i.category,i.title,i.snippet,i.url,i.published_at,
                s.model_score,s.reason
        FROM items i
        JOIN item_scores s ON s.item_id = i.id
        WHERE s.model_score >= %s
            AND (%s::text IS NULL OR i.category = %s)
        ORDER BY i.published_at DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cursor:
        cursor.execute(sql,(min_score,category,category,limit,offset))
        return [dict(zip([d[0] for d in cursor.description],row)) for row in cursor.fetchall()]

def semantic_search(conn:psycopg.Connection,query_vec:str,
                    limit:int=8,min_similarity:float=0.30,
                    category: str|None = None,since:datetime|None = None) -> list[dict]:
    """ pgvector cosine similarity search"""
    sql = """
        SELECT * FROM (
            SELECT i.id,i.category,i.title,i.snippet,i.url,i.published_at,
                    1-(i.embedding <=> %s::vector) AS similarity
            FROM items i
            WHERE i.embedding IS NOT NULL
                AND (%s::text IS NULL OR i.category = %s)
                AND (%s::timestamptz IS NULL OR i.published_at >= %s)
        ) t
        WHERE t.similarity >= %s
        ORDER BY t.similarity DESC
        LIMIT %s
    """
    with conn.cursor() as cursor:
        cursor.execute(sql,(query_vec,category,category,
                            since,since,min_similarity,limit))
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns,row)) for row in cursor.fetchall()]


# ---------- 用户 ----------

def ensure_user_table(conn: psycopg.Connection):
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(64) UNIQUE NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)
    conn.commit()

def count_users(conn: psycopg.Connection) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM users")
        return cursor.fetchone()[0]

def create_user(conn: psycopg.Connection, username: str, password: str) -> int:
    """密码经 PBKDF2 哈希后入库，明文不落库"""
    from src.api.auth import hash_password
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, hash_password(password)),
        )
        uid = cursor.fetchone()[0]
    conn.commit()
    return uid

def get_user_by_username(conn: psycopg.Connection, username: str) -> dict | None:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "password_hash": row[2]}
