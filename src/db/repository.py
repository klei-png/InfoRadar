import json
import logging
from datetime import datetime,timezone
from typing import Iterable
import psycopg

from src.models.schema import Item
from src.pipeline.dedup import url_hash as gen_url_hash, simhash64

logger = logging.getLogger(__name__)

def _clean_text(value: str|None) -> str|None:
    if value is None:
        return
    return value.replace("\x00","")

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

def fetch_candidates_for_agent(conn: psycopg.Connection,limit: int = 80) -> list[dict]:
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

def record_feedback(conn: psycopg.Connection, item_id: int | None,
                    digest_id: int | None, rating: int,
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
