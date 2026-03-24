"""Track active chat runs and pending tool approvals for AGUI."""

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


class ApprovalRegistry:
    """Store pending HITL approvals by (thread, run, tool_call)."""

    def __init__(self) -> None:
        self._pending: dict[tuple[str, str, str], asyncio.Future[bool]] = {}
        self._lock = asyncio.Lock()

    async def create(self, thread_id: str, run_id: str, tool_call_id: str) -> asyncio.Future[bool]:
        key = (thread_id, run_id, tool_call_id)
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        async with self._lock:
            self._pending[key] = fut
        return fut

    async def resolve(self, thread_id: str, run_id: str, tool_call_id: str, approved: bool) -> bool:
        key = (thread_id, run_id, tool_call_id)
        async with self._lock:
            fut = self._pending.pop(key, None)
        if fut is None:
            return False
        if not fut.done():
            fut.set_result(bool(approved))
        return True

    async def clear_run(self, thread_id: str, run_id: str) -> None:
        async with self._lock:
            keys = [k for k in self._pending if k[0] == thread_id and k[1] == run_id]
            futures = [self._pending.pop(k) for k in keys]
        for fut in futures:
            if not fut.done():
                fut.cancel()
