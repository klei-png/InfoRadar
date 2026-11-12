from datetime import date, timedelta
from fastapi import FastAPI,HTTPException,Query
from pydantic import BaseModel

from src.db.connection import get_conn
from src.db.repository import list_recent_digests,get_latest_digest,list_scored_items,record_feedback

app = FastAPI(title="InforRadar",version="0.1.0",
              description="Inforadar")

@app.get("/health")
def health():
    """ liveness probe"""
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    finally:
        conn.close()
    return {"status":"ok"}

@app.get("/digests")
def digests(days: int = Query(7,ge=1,le=90)):
    """ the briefing list for the past N days"""
    conn = get_conn()
    try:
        return list_recent_digests(conn,days=days)
    finally:
        conn.close()

@app.get("/digests/{category}")
def digest_by_category(category:str):
    """ the full text of the latest brief for the specified category"""
    conn = get_conn()
    try:
        d = get_latest_digest(conn,category)
    finally:
        conn.close()
    if d is None:
        raise HTTPException(404,f"no digest for category {category!r}")
    return d

@app.get("/items")
def items(category: str | None = None,
          min_score: int = Query(1,ge=0,le=10),
          limit: int = Query(50,ge=1,le=200),
          offset: int = Query(1,ge=0)):
    """"""
    conn = get_conn()
    try:
        result = list_scored_items(conn,category=category,min_score=min_score,
                                   limit=limit,offset=offset)
        return result
    finally:
        conn.close()

class FeedbackIn(BaseModel):
    item_id: int
    rating: int
    comment: str|None = None

@app.post("/feedback",status_code=201)
def feedback(body: FeedbackIn):
    """ record user feedback on entries"""
    if body.rating not in (-1,0,1):
        raise HTTPException(422,"rating must be one of -1/0/1")
    conn = get_conn()
    try:
        record_feedback(conn,item_id=body.item_id,rating=body.rating,comment=body.comment)
    finally:
        conn.close()
    return {"ok":True}