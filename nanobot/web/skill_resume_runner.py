from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event
from nanobot.web.skill_runtime_driver import run_skill_runtime_driver


# Reserved keys that ``skill_runtime_start`` envelopes carry as routing metadata.
# Anything *else* in ``payload`` (e.g. ``transition`` / ``transition_id``) is
# forwarded into the chained driver's ``request.result``, so handoff metadata
# from job_management/zhgk/jmfz reaches project_guide's stdin in the schema its
# driver already expects (see ``templates/project_guide/runtime/driver.py``).
_CHAIN_RESERVED_KEYS: frozenset[str] = frozenset({"skillName", "action", "requestId", "threadId"})

# Per-call recursion guard. ``project_guide`` is allowed to be started from any
# of the three phase drivers (handoff). The chain depth is bounded in practice
# (caller → 1 nested call), but we keep an explicit cap so a misbehaving driver
# can't fork-bomb the worker.
_CHAIN_MAX_DEPTH = 3


def _normalize_skill_first_action(*, skill_name: str, action: str) -> str:
    """Normalize legacy/generic actions to skill-specific driver entrypoints.

    ``skill_runtime_start`` is expected to provide a correct action name.
    For natural-language fast-path starts, keep compatibility with job_management's
    template entry action while allowing override via env.
    """
    sk = str(skill_name or "").strip().lower()
    act = str(action or "").strip()
    if sk in {"job_management", "job-management"} and act.lower() in {"start", "guide"}:
        import os

        return (os.environ.get("NANOBOT_JOB_MANAGEMENT_START_ACTION") or "").strip() or "jm_start"
    return act


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
        _chain_depth: int = 0,
        **_ignored: Any,
    ) -> dict[str, Any]:
        normalized_action = _normalize_skill_first_action(skill_name=skill_name, action=action)
        try:
            events = await run_skill_runtime_driver(
                skill_name=skill_name,
                request={
                    "thread_id": thread_id,
                    "skill_name": skill_name,
                    "request_id": request_id,
                    "action": normalized_action,
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
                ev_name = str(env.get("event") or "").strip()

                # Skill chaining: drivers can request the platform to start
                # another skill in the same turn (e.g. job_management /
                # zhgk / jmfz emit a ``skill_runtime_start`` envelope at
                # phase boundaries to wake up ``project_guide``). The
                # platform is the only seam that can spawn a skill driver
                # subprocess; instead of plumbing this through bridge
                # intents (which run from chat_card_intent / NL fast-path),
                # we re-enter the runner with handoff metadata flattened
                # into ``result`` so the chained driver's stdin schema
                # (``request.result.transition`` / ``transition_id``)
                # matches what its ``driver.py`` already reads.
                if ev_name == "skill_runtime_start":
                    handled = await _maybe_chain_start(
                        envelope=env,
                        parent_skill=skill_name,
                        parent_thread_id=thread_id,
                        chain_depth=_chain_depth,
                    )
                    if handled:
                        emitted += 1
                        continue
                    # Falls through to ``emit_skill_runtime_event`` which
                    # currently raises ``unsupported skill runtime event`` —
                    # callers should treat that as a programming error and
                    # surface the trace.

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

    async def _maybe_chain_start(
        *,
        envelope: dict[str, Any],
        parent_skill: str,
        parent_thread_id: str,
        chain_depth: int,
    ) -> bool:
        """Try to handle a ``skill_runtime_start`` envelope as a chained start.

        Returns ``True`` when the envelope was consumed (success or recoverable
        error); the caller should NOT fall through to ``emit_skill_runtime_event``
        in that case. Returns ``False`` only when the envelope is so malformed
        that we want it to surface via the default error path.
        """
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return False

        child_skill = str(payload.get("skillName") or "").strip()
        child_action = str(payload.get("action") or "").strip()
        if not child_skill or not child_action:
            logger.warning(
                "skill_runtime_start envelope dropped: missing skillName/action | parent={} payload_keys={}",
                parent_skill,
                sorted(payload.keys()),
            )
            return True  # Consume; fall-through would be a confusing ValueError.

        # Self-recursion guard: a driver should never start itself via
        # the chain seam (would loop forever on the same stdin schema).
        if child_skill == parent_skill:
            logger.warning(
                "skill_runtime_start envelope ignored (self-recursion) | skill={}",
                child_skill,
            )
            return True

        if chain_depth >= _CHAIN_MAX_DEPTH:
            logger.warning(
                "skill_runtime_start chain depth exceeded | parent={} child={} depth={}",
                parent_skill,
                child_skill,
                chain_depth,
            )
            return True

        # Forward every non-routing field into ``result``. ``transition`` and
        # ``transition_id`` are the canonical handoff fields today, but keeping
        # this generic means future fields (e.g. ``hint``, ``capabilities``)
        # don't need bridge changes.
        child_result: dict[str, Any] = {}
        for k, v in payload.items():
            if k in _CHAIN_RESERVED_KEYS:
                continue
            child_result[k] = v

        # Stable per-handoff request_id (transition_id-derived) keeps logs
        # auditable even when many phase boundaries fire in one session;
        # falls back to wall clock so we never collide between turns.
        explicit_rid = str(payload.get("requestId") or "").strip()
        explicit_tid = str(child_result.get("transition_id") or "").strip()
        if explicit_rid:
            child_request_id = explicit_rid
        elif explicit_tid:
            child_request_id = f"req-handoff-{child_skill}-{explicit_tid}"
        else:
            child_request_id = f"req-handoff-{child_skill}-{int(time.time() * 1000)}"

        child_thread = str(payload.get("threadId") or "").strip() or parent_thread_id

        logger.info(
            "skill chain start | parent={} child={} action={} request_id={} depth={}",
            parent_skill,
            child_skill,
            child_action,
            child_request_id,
            chain_depth + 1,
        )

        try:
            await _runner(
                thread_id=child_thread,
                skill_name=child_skill,
                request_id=child_request_id,
                action=child_action,
                status="ok",
                result=child_result,
                _chain_depth=chain_depth + 1,
            )
        except Exception:
            # Inner ``_runner`` already returns structured errors; bubbling here
            # would only happen for unanticipated bugs (and would crash the
            # parent driver's whole emit loop). Log + swallow keeps the parent
            # turn observable for the user.
            logger.exception(
                "skill chain start failed | parent={} child={} action={} request_id={}",
                parent_skill,
                child_skill,
                child_action,
                child_request_id,
            )
        return True

    return _runner

