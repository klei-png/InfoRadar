from fastapi import FastAPI,HTTPException,Query
from pydantic import BaseModel,Field

from src.llm.gateway import chat_with_meta,embed,LLMError
from src.db.connection import get_conn
from src.db.repository import (list_recent_digests,get_latest_digest,list_scored_items,
                               record_feedback,semantic_search)
from src.pipeline.embedding import vector_to_str

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


ASK_SYSTEM = """
你是信息助手，基于用户信息库中检索到的条目回答问题。
要求：
1. 只使用提供的条目内容回答，不要编造；条目不足以回答时直接说"库中没有足够信息"
2. 每条结论后用 [编号] 标注来源条目
3. 中文回答，简洁准确，200 字以内
"""
class AskIn(BaseModel):
    question: str = Field(min_length=2,max_length=500)
    category: str | None = None
    top_k: int = Field(8,ge=1,le=20)

@app.post("/ask")
async def ask(body:AskIn):
    """ RAG Q&A: vector retrieval + cite-aware generation"""
    try:
        question_vec = (await embed([body.question]))[0]
    except LLMError as e:
        raise HTTPException(502,f"embedding failed: {e}")

    conn = get_conn()
    try:
        hits = semantic_search(conn,vector_to_str(question_vec),
                               limit=body.top_k,category=body.category)
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
            [{"role":"system","content":ASK_SYSTEM},
             {"role":"user","content":f"条目:\n{context}\n\n问题:{body.question}"}],
            temperature=0.1,
        )
    except LLMError as e:
        raise HTTPException(502,f"llm failed: {e}")

    return {
        "answer":answer,
        "sources": [{"id": h["id"], "title": h["title"], "url": h["url"],
                     "similarity": round(h["similarity"], 3)} for h in hits],
        "usage":meta,
    }