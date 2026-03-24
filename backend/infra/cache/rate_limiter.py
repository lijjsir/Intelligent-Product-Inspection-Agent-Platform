from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.core.config import settings

class RateLimiter:
    _windows: dict[str, deque[float]] = defaultdict(deque)
    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, rpm: int | None = None):
        self._rpm = rpm or settings.rate_limit_rpm_default

    async def allow(self, key: str) -> bool:
        if self._rpm <= 0:
            return True
        async with self._lock_for(key):
            window = self._windows[key]
            self._evict_expired(window)
            return len(window) < self._rpm

    async def reserve(self, key: str) -> bool:
        if self._rpm <= 0:
            return True
        async with self._lock_for(key):
            window = self._windows[key]
            self._evict_expired(window)
            if len(window) >= self._rpm:
                return False
            window.append(time.monotonic())
            return True

    @classmethod
    def reset(cls) -> None:
        cls._windows.clear()
        cls._locks.clear()

    @classmethod
    def _lock_for(cls, key: str) -> asyncio.Lock:
        lock = cls._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[key] = lock
        return lock

    @staticmethod
    def _evict_expired(window: deque[float]) -> None:
        threshold = time.monotonic() - 60.0
        while window and window[0] <= threshold:
            window.popleft()
