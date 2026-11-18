from enum import Enum

class RunStatus(str,Enum):

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"

    NEEDS_ATTENTION = "needs_attention"
    WAITING_APPROVAL = "waiting_approval"

    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    REJECTED = "rejected"

TERMINAL = frozenset({
    RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED,
    RunStatus.TIMEOUT, RunStatus.REJECTED
})
PAUSED = frozenset({RunStatus.NEEDS_ATTENTION,RunStatus.WAITING_APPROVAL})