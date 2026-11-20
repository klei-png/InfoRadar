import asyncio

from src.agent.policy import Policy
from src.agent.tool_executor import ToolExecutor
from src.agent.types import Evidence, RunContext, RunState, ToolCall
from src.tools.defaults import default_registry
from src.tools.base import ToolResult

def _run(coro):
    return asyncio.run(coro)

def _executor() -> ToolExecutor:
    return ToolExecutor(default_registry, Policy())

def test_default_tools_registered():
    names = default_registry.names()
    for t in ("web_search", "fetch_page", "kb_search", "read_evidence"):
        assert t in names, f"缺工具: {t}"

def test_read_evidence_summary():
    ctx = RunContext(run_id="r1", state=RunState(run_id="r1", evidence=[
        Evidence(evidence_id="EV-1", source="web", url="https://a.com/x",
                 summary="要点摘要", content_ref="event:r1:7"),
    ]))
    r = _run(_executor().execute(ToolCall(call_id="c1", name="read_evidence",
                                          arguments={"evidence_id": "EV-1"}), ctx=ctx))
    assert r.ok and "EV-1" in r.content and "要点摘要" in r.content

def test_read_evidence_missing():
    ctx = RunContext(run_id="r1", state=RunState(run_id="r1"))
    r = _run(_executor().execute(ToolCall(call_id="c2", name="read_evidence",
                                          arguments={"evidence_id": "EV-9"}), ctx=ctx))
    assert not r.ok and "不存在" in r.content

def test_read_evidence_without_ctx():
    r = _run(_executor().execute(ToolCall(call_id="c3", name="read_evidence",
                                          arguments={"evidence_id": "EV-1"})))
    assert not r.ok and "上下文" in r.content

def test_fetch_page_blocks_loopback():
    r = _run(_executor().execute(ToolCall(call_id="c4", name="fetch_page",
                                          arguments={"url": "http://127.0.0.1:5432/"})))
    assert not r.ok and "SSRF" in r.content

def test_fetch_page_blocks_file_scheme():
    r = _run(_executor().execute(ToolCall(call_id="c5", name="fetch_page",
                                          arguments={"url": "file:///etc/passwd"})))
    assert not r.ok and "scheme" in r.content

def test_fetch_page_blocks_metadata_ip():
    r = _run(_executor().execute(ToolCall(call_id="c6", name="fetch_page",
                                          arguments={"url": "http://169.254.169.254/latest/meta-data/"})))
    assert not r.ok and "SSRF" in r.content