from __future__ import annotations

import json
import logging
from msvcrt import kbhit

from src.tools.base import Tool,ToolDefinition,ToolResult

logger = logging.getLogger(__name__)

def build_read_evidence_tool() -> Tool:
    async def read_evidence(evidence_id: str, _ctx=None) -> ToolResult:
        if _ctx is None:
            return ToolResult(
                ok=False,
                content=f"read_evidence 需要运行上下文",
                error_code="E_TOOL_FAILED",
            )
        ev = next((e for e in _ctx.state.evidence if e.evidence_id == evidence_id), None)
        if ev is None:
            ids = [e.evidence_id for e in _ctx.state.evidence]
            return ToolResult(ok=False,
                              content=f"证据{evidence_id}不存在，可用：{ids}",
                              error_code="E_TOOL_FAILED")
        if ev.content_ref and _ctx.store is not None:
            try:
                _,run_id,seq = ev.content_ref.split(":")
                ev_obj = await _ctx.store.get_event(run_id,int(seq))
                if ev_obj is not None and ev_obj.data.get("content"):
                    return ToolResult(ok=True,content=ev_obj.data["content"])
            except Exception as e:
                logger.warning("read_evidence 全文获取失败(%s): %s", ev.content_ref, e)
        return ToolResult(ok=True, content=json.dumps(
            {"evidence_id":ev.evidence_id,"source": ev.source,"url":ev.url,
             "summary": ev.summary, "content_ref": ev.content_ref},
            ensure_ascii=False))

    return Tool(
        defn=ToolDefinition(
            name="read_evidence",
            description="按 evidence_id 读取本任务已收集证据的摘要或全文",
            input_schema={
                "type": "object",
                "required": ["evidence_id"],
                "properties": {"evidence_id": {"type": "string"}},
            },
            permission="read",
        ),
        handler=read_evidence,
    )