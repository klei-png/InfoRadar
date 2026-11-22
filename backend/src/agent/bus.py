"""agent/bus.py — 进程内实时事件总线（M3 块③）。

TOKEN 打字机增量不落库（账本数据一律走 store，事件流保持干净），
只在订阅瞬间实时推送——发布/订阅模式，发布者永不被慢消费者阻塞。
"""
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
        """同步非阻塞：SSE 慢消费者丢增量即可（打字机可容忍缺口），
        绝不让模型调用等任何订阅者——持久化层的数据不经过这里。"""
        for q in list(self._subs.get(run_id, ())):
            try:
                q.put_nowait(delta)
            except asyncio.QueueFull:
                pass
