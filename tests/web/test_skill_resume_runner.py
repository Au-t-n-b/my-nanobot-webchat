"""Tests for skill-first resume runner."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_skill_first_resume_runner_runs_driver_and_emits_events(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[dict] = []

    async def fake_emit_skill_runtime_event(
        *, envelope, thread_id, docman=None, pending_hitl_store=None, agent_loop=None
    ):
        emitted.append({"envelope": envelope, "thread_id": thread_id})
        return {"ok": True, "event": envelope.get("event"), "summary": "ok"}

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        return [
            {
                "event": "chat.guidance",
                "payload": {"context": "hi", "actions": []},
            }
        ]

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    runner = make_skill_first_resume_runner(pending_hitl_store=object())
    out = await runner(
        thread_id="t-1",
        skill_name="demo_skill",
        request_id="req-1",
        action="after_choice",
        status="ok",
        result={"selected": "a"},
    )

    assert out["ok"] is True
    assert out["emitted_count"] == 1
    assert emitted[0]["thread_id"] == "t-1"
    assert emitted[0]["envelope"]["event"] == "chat.guidance"


@pytest.mark.asyncio
async def test_skill_first_resume_runner_normalizes_job_management_start_to_jm_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_emit_skill_runtime_event(
        *, envelope, thread_id, docman=None, pending_hitl_store=None, agent_loop=None
    ):
        return {"ok": True, "event": envelope.get("event"), "summary": "ok"}

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        captured.clear()
        captured.update(dict(request))
        return []

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    runner = make_skill_first_resume_runner(pending_hitl_store=object())
    out = await runner(
        thread_id="t-1",
        skill_name="job_management",
        request_id="req-1",
        action="start",
        status="ok",
        result={},
    )

    assert out["ok"] is True
    assert captured.get("action") == "jm_start"


# ---------------------------------------------------------------------------
# Skill chain (handoff) tests
# ---------------------------------------------------------------------------
#
# When a phase driver (job_management / zhgk / jmfz) finishes its last task it
# emits ``event=skill_runtime_start`` with ``payload.skillName="project_guide"``
# plus ``payload.transition`` / ``payload.transition_id``. The resume runner is
# the only seam that can spawn a skill driver subprocess, so it re-enters
# itself for the chained skill, flattening every non-routing payload field
# into ``request.result`` (project_guide's driver reads
# ``request.result.transition`` / ``transition_id``). These tests verify that
# wiring without touching real subprocesses.


@pytest.mark.asyncio
async def test_skill_chain_starts_project_guide_with_transition_in_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driver emits ``skill_runtime_start`` envelope → runner spawns chained
    driver with ``transition`` / ``transition_id`` flattened into ``result``."""

    driver_invocations: list[dict] = []

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        driver_invocations.append({"skill_name": skill_name, "request": dict(request)})
        # First (parent) call: job_management completes and asks platform to
        # wake up project_guide. Second (chained) call: project_guide driver
        # itself, which we let succeed silently.
        if skill_name == "job_management":
            return [
                {
                    "event": "skill_runtime_start",
                    "threadId": "t-handoff",
                    "skillRunId": "run-jm-1",
                    "timestamp": 1700000000000,
                    "payload": {
                        "skillName": "project_guide",
                        "action": "guide_next_phase",
                        "transition": {
                            "from_module": "job_management",
                            "to_module": "smart_survey",
                        },
                        "transition_id": "job_management->smart_survey@1700000000000",
                    },
                }
            ]
        return []

    async def fake_emit_skill_runtime_event(
        *, envelope, thread_id, docman=None, pending_hitl_store=None, agent_loop=None
    ):
        # The chain seam should fully consume ``skill_runtime_start`` envelopes,
        # so the bridge emit handler must NEVER see one. If it does, that's a
        # regression: we'd be falling through to ``unsupported skill runtime
        # event`` and crashing the parent driver's emit loop.
        assert envelope.get("event") != "skill_runtime_start", (
            "skill_runtime_start envelope leaked to bridge.emit_skill_runtime_event "
            "instead of being handled by the chain seam"
        )
        return {"ok": True, "event": envelope.get("event")}

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    runner = make_skill_first_resume_runner(pending_hitl_store=object())
    out = await runner(
        thread_id="t-handoff",
        skill_name="job_management",
        request_id="req-jm-1",
        action="some_terminal_action",
        status="ok",
        result={},
    )

    assert out["ok"] is True
    # Two driver subprocess invocations: parent + chained child.
    assert len(driver_invocations) == 2
    parent, child = driver_invocations
    assert parent["skill_name"] == "job_management"
    assert child["skill_name"] == "project_guide"

    child_request = child["request"]
    assert child_request["action"] == "guide_next_phase"
    # ``request_id`` is derived from transition_id (auditable per-handoff).
    assert child_request["request_id"] == (
        "req-handoff-project_guide-job_management->smart_survey@1700000000000"
    )

    # The flattened ``result`` is exactly what
    # ``templates/project_guide/runtime/driver.py`` reads on stdin.
    child_result = child_request["result"]
    assert child_result["transition"] == {
        "from_module": "job_management",
        "to_module": "smart_survey",
    }
    assert child_result["transition_id"] == "job_management->smart_survey@1700000000000"
    # Routing keys must NOT bleed into ``result`` (they go on the request envelope).
    assert "skillName" not in child_result
    assert "action" not in child_result


@pytest.mark.asyncio
async def test_skill_chain_self_recursion_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A driver that mistakenly emits a ``skill_runtime_start`` pointing at
    itself must not loop. Resume runner detects ``child_skill == parent_skill``
    and drops the envelope (loud warning, but no crash and no infinite spawn)."""

    invocations: list[str] = []

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        invocations.append(skill_name)
        # A buggy driver tells the platform to start itself again.
        return [
            {
                "event": "skill_runtime_start",
                "payload": {
                    "skillName": "buggy_skill",
                    "action": "loop",
                    "transition_id": "x",
                },
            }
        ]

    async def fake_emit_skill_runtime_event(*, envelope, thread_id, **_):
        return {"ok": True}

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    runner = make_skill_first_resume_runner(pending_hitl_store=object())
    out = await runner(
        thread_id="t-1",
        skill_name="buggy_skill",
        request_id="req-1",
        action="start",
        status="ok",
        result={},
    )

    assert out["ok"] is True
    # Self-recursion guard kicks in → only the parent driver subprocess runs.
    assert invocations == ["buggy_skill"]


@pytest.mark.asyncio
async def test_skill_chain_max_depth_caps_recursion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two distinct skills bouncing handoffs back and forth would otherwise
    spawn forever. ``_CHAIN_MAX_DEPTH`` caps the chain at 3 levels."""

    invocations: list[str] = []

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        invocations.append(skill_name)
        # Each driver hands off to "the other one" (a → b → a → b → ...).
        other = "skill_b" if skill_name == "skill_a" else "skill_a"
        return [
            {
                "event": "skill_runtime_start",
                "payload": {"skillName": other, "action": "next"},
            }
        ]

    async def fake_emit_skill_runtime_event(*, envelope, thread_id, **_):
        return {"ok": True}

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_resume_runner import _CHAIN_MAX_DEPTH, make_skill_first_resume_runner

    runner = make_skill_first_resume_runner(pending_hitl_store=object())
    out = await runner(
        thread_id="t-1",
        skill_name="skill_a",
        request_id="req-1",
        action="start",
        status="ok",
        result={},
    )

    assert out["ok"] is True
    # Chain visits parent (depth 0) + at most _CHAIN_MAX_DEPTH children.
    assert len(invocations) == _CHAIN_MAX_DEPTH + 1


@pytest.mark.asyncio
async def test_skill_chain_passthrough_ignores_non_chain_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``chat.guidance`` and other event types must continue to flow through
    ``emit_skill_runtime_event`` unchanged when chain support is added."""

    bridge_calls: list[str] = []

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        return [
            {"event": "chat.guidance", "payload": {"context": "x"}},
            {"event": "task_progress.sync", "payload": {"modules": []}},
        ]

    async def fake_emit_skill_runtime_event(*, envelope, thread_id, **_):
        bridge_calls.append(envelope.get("event"))
        return {"ok": True}

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    runner = make_skill_first_resume_runner(pending_hitl_store=object())
    out = await runner(
        thread_id="t-1",
        skill_name="zhgk",
        request_id="req-1",
        action="start",
        status="ok",
        result={},
    )

    assert out["ok"] is True
    assert bridge_calls == ["chat.guidance", "task_progress.sync"]

