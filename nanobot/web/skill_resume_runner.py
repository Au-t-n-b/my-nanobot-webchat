from __future__ import annotations

from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event
from nanobot.web.skill_runtime_driver import run_skill_runtime_driver


def make_skill_first_resume_runner(
    *,
    pending_hitl_store: Any,
    docman: Any = None,
    python_executable: str | None = None,
    agent_loop: Any = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Create a pure skill-first resume runner.

    Minimal behavior:
    - Run `<skill_dir>/runtime/driver.py` with the resume request JSON
    - Collect emitted envelopes (JSON lines)
    - Re-dispatch each envelope through `emit_skill_runtime_event` to reuse platform primitives
    """

    async def _runner(
        *,
        thread_id: str,
        skill_name: str,
        request_id: str,
        action: str,
        status: str,
        result: Any,
        **_ignored: Any,
    ) -> dict[str, Any]:
        try:
            events = await run_skill_runtime_driver(
                skill_name=skill_name,
                request={
                    "thread_id": thread_id,
                    "skill_name": skill_name,
                    "request_id": request_id,
                    "action": action,
                    "status": status,
                    "result": result,
                },
                python_executable=python_executable,
            )
        except Exception as e:
            logger.exception(
                "skill_first resume driver failed | thread_id={} skill_name={} request_id={} action={}",
                thread_id,
                skill_name,
                request_id,
                action,
            )
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

        emitted = 0
        try:
            for env in events:
                if not isinstance(env, dict):
                    continue
                await emit_skill_runtime_event(
                    envelope=env,
                    thread_id=thread_id,
                    docman=docman,
                    pending_hitl_store=pending_hitl_store,
                    agent_loop=agent_loop,
                )
                emitted += 1
        except Exception as e:
            logger.exception(
                "skill_first resume emit failed | thread_id={} skill_name={} request_id={} action={} emitted={}",
                thread_id,
                skill_name,
                request_id,
                action,
                emitted,
            )
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "emitted_count": emitted}

        return {"ok": True, "emitted_count": emitted}

    return _runner

