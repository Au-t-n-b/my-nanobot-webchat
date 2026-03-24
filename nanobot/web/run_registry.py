"""Track active chat runs per threadId (HTTP 409 when overlapping)."""

from __future__ import annotations

import asyncio


class RunRegistry:
    """At most one active run per threadId."""

    def __init__(self) -> None:
        self._active: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def try_begin(self, thread_id: str, run_id: str) -> bool:
        async with self._lock:
            if thread_id in self._active:
                return False
            self._active[thread_id] = run_id
            return True

    async def end(self, thread_id: str) -> None:
        async with self._lock:
            self._active.pop(thread_id, None)
