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
async def test_skill_first_resume_runner_keeps_action_passthrough(
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
    assert captured.get("action") == "start"

