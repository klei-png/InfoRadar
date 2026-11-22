from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from src.agent.status import RunStatus
from src.agent.tool_executor import ToolExecutor
from src.agent.types import RunConfig, RunState, ToolCall, RunStore, ExecutionLedger


@dataclass
class RecoverPlan:
    action: str
    state: RunState | None = None
    pending: list[ToolCall] = field(default_factory=list)
    error_code: str | None = None


class Recovery:
    def __init__(self, store: RunStore, ledger: ExecutionLedger, toolx: ToolExecutor) -> None:
        self._store = store
        self._ledger = ledger
        self._toolx = toolx

    async def plan(self, run_id: str, config: RunConfig) -> RecoverPlan:
        cp = await self._store.load_checkpoint(run_id)
        if cp is None:
            return RecoverPlan(action="failed", error_code="E_RECOVER_FAILED")


        if (json.dumps(cp.state.config_snapshot, sort_keys=True)
                != json.dumps(config.model_dump(), sort_keys=True)):
            return RecoverPlan(action="failed", error_code="E_RECOVER_CONFIG_DRIFT")

        pending = list(cp.pending_tool_calls)
        for tc in pending:
            tool = self._toolx.precheck(tc.name)
            if (tool is not None and tool.defn.side_effect
                    and tool.defn.recovery_strategy == "manual"):

                idem = hashlib.sha256(f"{run_id}{tc.call_id}".encode()).hexdigest()
                rec = await self._ledger.get_execution(run_id, idem)
                if rec is not None and rec["status"] == "executing":
                    await self._ledger.mark_unknown(rec["id"])
                    await self._store.save_run_meta(
                        run_id, status=RunStatus.NEEDS_ATTENTION.value)
                    return RecoverPlan(action="needs_attention",
                                       error_code="E_UNKNOWN_SIDE_EFFECT")

        return RecoverPlan(action="resume", state=cp.state, pending=pending)
