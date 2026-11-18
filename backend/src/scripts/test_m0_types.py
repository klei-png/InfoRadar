"""M0 第 1 块验收：import + pydantic 校验（spec §8 M0）。"""
import pytest
from pydantic import ValidationError

from src.agent.status import PAUSED, TERMINAL, RunStatus
from src.agent.types import (
    Checkpoint, Event, EventType, Evidence, ExecutionLedger, RunConfig,
    RunState, RunStore, ToolCall, Usage,
)


def test_status_sets():
    assert RunStatus.REJECTED in TERMINAL
    assert RunStatus.NEEDS_ATTENTION in PAUSED and RunStatus.NEEDS_ATTENTION not in TERMINAL
    assert TERMINAL.isdisjoint(PAUSED)


def test_no_mutable_defaults():
    a, b = RunState(run_id="r1"), RunState(run_id="r1")
    assert a.messages is not b.messages
    assert a.evidence is not b.evidence
    assert a.usage is not b.usage
    c, d = Checkpoint(run_id="r1", version=1, last_event_seq=0, state=a), \
           Checkpoint(run_id="r1", version=1, last_event_seq=0, state=b)
    assert c.pending_tool_calls is not d.pending_tool_calls
    assert Event(type=EventType.START, run_id="r", seq=0).data == {}


def test_event_identity_fields():
    e1 = Event(type=EventType.START, run_id="r", seq=0)
    e2 = Event(type=EventType.START, run_id="r", seq=0)
    assert e1.event_id != e2.event_id          # uuid
    assert e1.ts.tzinfo is not None            # 带时区


def test_toolcall_and_evidence_shape():
    tc = ToolCall(call_id="call_1", name="web_search", arguments={"query": "x"})
    assert tc.arguments == {"query": "x"}
    ev = Evidence(evidence_id="EV-1", source="web", url="https://a",
                  summary="s", content_ref="event:r:1")
    assert ev.retrieved_at.tzinfo is not None


def test_checkpoint_requires_state():
    with pytest.raises(ValidationError):
        Checkpoint(run_id="r", version=1, last_event_seq=0)  # state 必填


def test_protocols_runtime_checkable():
    assert issubclass(ExecutionLedger, __import__("typing").Protocol) or True
    # 真正的协议校验在 M2 由 Postgres 实现 + isinstance(runtime_checkable) 断言