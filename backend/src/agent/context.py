from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel

from src.agent.types import RunState


class ContextPolicy(BaseModel):
    max_context_chars: int = 200_000
    compress_ratio: float = 0.8
    keep_recent_rounds: int = 2
    compress_tool_result_over: int = 120


def estimate_chars(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content") or ""
        total += len(c) if isinstance(c, str) else len(str(c))
        if m.get("tool_calls"):
            total += len(json.dumps(m["tool_calls"], ensure_ascii=False))
    return total


@dataclass
class CompactionResult:
    rounds_total: int
    rounds_kept: int
    compressed_msgs: int
    chars_before: int
    chars_after: int


class ContextManager:
    def __init__(self, policy: ContextPolicy | None = None) -> None:
        self._p = policy or ContextPolicy()

    def needs_compaction(self, messages: list[dict]) -> bool:
        return estimate_chars(messages) > self._p.max_context_chars * self._p.compress_ratio

    def compact(self, state: RunState) -> CompactionResult | None:
        msgs = state.messages
        if not self.needs_compaction(msgs):
            return None
        before = estimate_chars(msgs)

        starts = [i for i, m in enumerate(msgs)
                  if m.get("role") == "assistant" and m.get("tool_calls")]
        if len(starts) <= self._p.keep_recent_rounds:
            return None

        header_end = starts[0]
        cutoff = starts[-self._p.keep_recent_rounds]

        compressed = 0
        for i in range(header_end, cutoff):
            m = msgs[i]
            if m.get("role") == "tool" and isinstance(m.get("content"), str) \
                    and len(m["content"]) > self._p.compress_tool_result_over:
                head = m["content"][:self._p.compress_tool_result_over]
                msgs[i] = {**m, "content":
                           f"{head}…[上下文压缩：此工具结果全文已移除，"
                           "如需详情可调 read_evidence（查 state.evidence）或重新调用该工具]"}
                compressed += 1

        after = estimate_chars(msgs)
        return CompactionResult(
            rounds_total=len(starts), rounds_kept=self._p.keep_recent_rounds,
            compressed_msgs=compressed, chars_before=before, chars_after=after)
