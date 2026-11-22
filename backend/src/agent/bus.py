from __future__ import annotations

import asyncio
from collections import defaultdict


class TokenBus:
    def __init__(self, max_queue: int = 2000) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._max_queue = max_queue

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self._subs[run_id].discard(q)

    def publish(self, run_id: str, delta: str) -> None:
        for q in list(self._subs.get(run_id, ())):
            try:
                q.put_nowait(delta)
            except asyncio.QueueFull:
                pass
