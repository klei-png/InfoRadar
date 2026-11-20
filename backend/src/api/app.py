from fastapi import FastAPI,HTTPException,Query,Depends
from pydantic import BaseModel,Field
from datetime import datetime
from pathlib import Path
from fastapi.staticfiles import StaticFiles

import asyncio

from src.llm.gateway import chat_with_meta,embed,LLMError
from src.db.connection import get_conn
from src.db.repository import (list_recent_digests,get_latest_digest,list_scored_items,
                               record_feedback,semantic_search,get_user_by_username)
from src.pipeline.embedding import vector_to_str
from src.pipeline.runner import run_once
from src.agents.scorer import run_scoring
from src.agents.digest import run_digest
from src.prompts.registry import get_prompt
from src.api.auth import require_auth,auth_enabled,create_token,verify_password




app = FastAPI(title="InforRadar",version="0.1.0",
              description="Inforadar")

class LoginIn(BaseModel):
    username: str = "admin"
    password: str


class AskIn(BaseModel):
    question: str = Field(min_length=2,max_length=500)
    category: str | None = None
    since: datetime | None = None
    top_k: int = Field(8,ge=1,le=20)


@app.post("/login")
def login(body: LoginIn):
    if not auth_enabled():
        return {"token":"no-auth"}
    conn = get_conn()
    try:
        user = get_user_by_username(conn, body.username)
    finally:
        conn.close()
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401,"用户名或密码错误")
    return {"token": create_token(body.username)}


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
def digests(days: int = Query(7,ge=1,le=90),_:None = Depends(require_auth)):
    """ the briefing list for the past N days"""
    conn = get_conn()
    try:
        return list_recent_digests(conn,days=days)
    finally:
        conn.close()


# 手动生成互斥锁：同一时刻只允许一个全链路生成任务（并发请求返回 409）
_generate_lock = asyncio.Lock()

@app.post("/digests/generate")
async def generate_digest(_:None = Depends(require_auth)):
    """ manually trigger the full pipeline: fetch -> scoring -> digest (about 1~3 min)"""
    if _generate_lock.locked():
        raise HTTPException(409,"已有生成任务进行中，请稍后再试")
    async with _generate_lock:
        fetched = await run_once()                      # 采集 + 入库 + 向量化
        scored = await run_scoring(limit=100)           # LLM 打分
        digested = await run_digest(min_score=7, hours=24)  # 分块摘要
    return {
        "fetched": fetched["fetched"],
        "inserted": fetched["inserted"],
        "scored": scored.get("scored", 0),
        "digests": digested["digests"],
    }

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
          offset: int = Query(0,ge=0),
          _:None = Depends(require_auth)):
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
def feedback(body: FeedbackIn,_:None = Depends(require_auth)):
    """ record user feedback on entries"""
    if body.rating not in (-1,0,1):
        raise HTTPException(422,"rating must be one of -1/0/1")
    conn = get_conn()
    try:
        record_feedback(conn,item_id=body.item_id,rating=body.rating,comment=body.comment)
    finally:
        conn.close()
    return {"ok":True}


@app.post("/ask")
async def ask(body:AskIn,_:None = Depends(require_auth)):
    """ RAG Q&A: vector retrieval + cite-aware generation"""
    try:
        question_vec = (await embed([body.question]))[0]
    except LLMError as e:
        raise HTTPException(502,f"embedding failed: {e}")

    conn = get_conn()
    try:
        hits = semantic_search(conn,vector_to_str(question_vec),
                               limit=body.top_k,category=body.category,
                               since=body.since)
    finally:
        conn.close()

    if not hits:
        return {"answer":"库中没有足够信息回答这个问题","sources":[]}

    context = "\n\n".join(
        f"[{h['id']}] {h['title']}\n{(h.get('snippet')or'')[:200]}\n链接: {h['url']}"
        for h in hits
    )
    try:
        answer,meta = await chat_with_meta(
            [{"role":"system","content":get_prompt("ask").system},
             {"role":"user","content":f"条目:\n{context}\n\n问题:{body.question}"}],
            temperature=0.1,
        )
    except LLMError as e:
        raise HTTPException(502,f"llm failed: {e}")

    return {
        "answer":answer,
        "sources": [{"id": h["id"], "title": h["title"], "url": h["url"],"published_at":h["published_at"],
                     "similarity": round(h["similarity"], 3)} for h in hits],
        "usage":meta,
    }

# 构建产物目录：本地 = 项目根/frontend/dist，容器 = /frontend/dist
app.mount("/",StaticFiles(directory=Path(__file__).resolve().parents[3] / "frontend" / "dist",
                          html=True,check_dir=False),name="static")