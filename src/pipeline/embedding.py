import logging

import psycopg

from src.db.connection import get_conn
from src.llm.gateway import embed

logger = logging.getLogger(__name__)

def vector_to_str(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:0.6f}" for x in vec) + "]"

async def embed_pending_items(conn: psycopg.Connection, batch: int = 48) -> int:
    """generate embeddings for entries that don't have them yet (using the title + snippet)
        combined as the text"""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id,title,snippet FROM items WHERE embedding IS NULL LIMIT %s",
            (batch,),
        )
        rows = cursor.fetchall()
    if not rows:
        return 0
    texts = [f"{r[1]}\n{r[2] or ''}" for r in rows]
    vectors = await embed(texts)

    with conn.cursor() as cursor:
        for (item_id,_,_),vec in zip(rows,vectors):
            cursor.execute(
                "UPDATE items SET embedding = %s::vector WHERE id=%s",
                (vector_to_str(vec),item_id)
            )
    conn.commit()
    logger.info("embedding %d item(s)",len(rows))
    return len(rows)

if __name__ == "__main__":
    import asyncio
    from src.db.connection import get_conn

    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(embed_pending_items(get_conn())))
