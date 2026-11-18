from __future__ import annotations

from datetime import datetime,timezone
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from litellm.harness import ToolCall
from pydantic import BaseModel, Field

from src.agent.status import RunStatus

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

#------------Basic value object---------------
class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cost_usd += other.cost_usd

class Evidence(BaseModel):
    evidence_id: str
    source: str
    url: str | None = None
    summary: str
    content_ref: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)

class RunConfig(BaseModel):
    max_rounds: int = 12
    wall_timeout: float = 300.0
    model: str | None = None
    token_budget: int | None =None
    allowed_tools: list[str] | None = None
    config_version: str = "1"

class RunState(BaseModel):
    run_id: str
    messages: list[dict[str,Any]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    rounds: int = 0
    usage: Usage = Field(default_factory=Usage)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    model_version: str | None = None
    tools_version: str | None = None

class Checkpoint(BaseModel):
    run_id: str
    checkpoint_id: str = Field(default_factory=lambda: uuid4().hex)
    version: int
    last_event_seq: int
    state: RunState
    pending_tool_calls: list[ToolCall] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

#----------events----------
class EventType(str, Enum):
    RUN_QUEUED = "run_queued"
    RUN_REJECTED = "run_rejected"
    START = "start"
    ROUND_START = "round_start"
    ROUND_END = "round_end"
    DECISION_SUMMARY = "decision_summary"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_DENIED = "tool_denied"
    CHECKPOINT = "checkpoint"
    ATTENTION_REQUIRED = "attention_required"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RESOLVED = "approval_resolved"
    RETRY = "retry"
    CONTEXT_COMPACTED = "context_compacted"
    USAGE = "usage"
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    type: EventType
    run_id: str
    seq: int
    ts: datetime = Field(default_factory=utcnow)
    data: dict[str, Any] = Field(default_factory=dict)



#---------persistence protocol----------
@runtime_checkable
class ExecutionLedger(Protocol):
    """ side effects execution registry is used to handle persistence
        the source of side effect facts comes from the Ledger, not the event stream
    """
    async def create_execution(self,run_id: str, tool_name: str, idem_key: str, args_digest: str) -> int: ...
    async def start_attempt(self,execution_id: int) -> int: ...
    async def finish_attempt(self,attempt_id: int, ok: bool, result_digest: str | None,
                             error_code: str | None) -> None: ...
    async def complete_execution(self, execution_id: int, status: Literal["succeeded","failed","unknown"],
                                 result_digest: str | None) -> None: ...
    async def mark_unknown(self, execution_id: int) -> None: ...
    async def get_execution(self, run_id: str,item_key: str) -> dict[str, Any] | None: ...

@runtime_checkable
class RunStore(Protocol):
    """
        run controls the persistence protocol for state/messages/events/checkpoints.
        writing the final state must go through transition_terminal atomic contention
    """
    async def create_run(self,task: str, config: RunConfig, owner: str) -> str: ...
    async def append_events(self, run_id: str, events: list[Event]): ...
    async def append_messages(self, run_id: str, msgs: list[dict[str, Any]], checkpoint: bool) -> None: ...
    async def save_checkpoint(self, cp: Checkpoint) -> None: ...
    async def load_checkpoint(self, run_id: str) -> Checkpoint | None: ...
    async def save_run_meta(self, run_id: str, **fields: Any) -> None: ...
    async def transition_terminal(self, run_id: str, status: RunStatus,
                                  error_code: str | None = None) -> bool: ...
    async def get_event(self, run_id: str, seq: int) -> Event | None: ...
