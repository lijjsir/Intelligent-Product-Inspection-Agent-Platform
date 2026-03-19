from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import AsyncIterator


class TaskStreamBroker:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._lock = asyncio.Lock()

    async def publish(self, task_id: str, event: dict) -> None:
        async with self._lock:
            self._history[task_id].append(event)
            queues = list(self._queues.get(task_id, set()))
        for q in queues:
            await q.put(event)

    async def subscribe(self, task_id: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._queues[task_id].add(q)
            history = list(self._history.get(task_id, []))
        for item in history:
            yield item
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            async with self._lock:
                self._queues[task_id].discard(q)


stream_broker = TaskStreamBroker()
