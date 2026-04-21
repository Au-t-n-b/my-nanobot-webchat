"""Tests for hybrid mode ``skill.agent_task_execute`` runtime bridge."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_skill_agent_task_execute_missing_goal() -> None:
    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    out = await emit_skill_runtime_event(
        envelope={
            "event": "skill.agent_task_execute",
            "skillName": "gongkan_skill",
            "payload": {
                "taskId": "x",
                "stepId": "s",
                "goal": "",
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:runtime",
            },
        },
        thread_id="t-miss",
        agent_loop=None,
    )
    assert out.get("ok") is False
    assert out.get("error") == "missing_goal"


@pytest.mark.asyncio
async def test_skill_agent_task_execute_skips_when_no_agent_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    task_payloads: list[dict[str, Any]] = []

    async def capture_task_status(payload: dict[str, Any]) -> None:
        task_payloads.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_task_status_event", capture_task_status)

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    out = await emit_skill_runtime_event(
        envelope={
            "event": "skill.agent_task_execute",
            "skillName": "gongkan_skill",
            "payload": {
                "taskId": "req:hybrid:1",
                "stepId": "zhgk.step1.hybrid",
                "goal": "只做占位，无 Agent 时应跳过模型调用",
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:runtime",
            },
        },
        thread_id="t-skip",
        agent_loop=None,
    )
    assert out.get("ok") is True
    assert out.get("skipped") is True
    assert task_payloads, "expected one task_progress sync"
    mod = task_payloads[0]["modules"][0]
    assert mod["id"] == "hybrid:gongkan_skill"
    assert mod["status"] == "skipped"


@pytest.mark.asyncio
async def test_skill_agent_task_execute_runs_subtask_and_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    task_payloads: list[dict[str, Any]] = []
    patch_payloads: list[dict[str, Any]] = []

    async def capture_task_status(payload: dict[str, Any]) -> None:
        task_payloads.append(payload)

    async def capture_patch(payload: dict[str, Any]) -> None:
        patch_payloads.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_task_status_event", capture_task_status)
    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", capture_patch)

    async def fake_run_hybrid(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "text": "集成测试：子任务结论文本"}

    monkeypatch.setattr("nanobot.web.hybrid_agent_subtask.run_hybrid_agent_subtask", fake_run_hybrid)

    class _FakeAgentLoop:
        provider = object()
        model = "fake-model"
        workspace = __import__("pathlib").Path("/tmp")
        restrict_to_workspace = False

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    out = await emit_skill_runtime_event(
        envelope={
            "event": "skill.agent_task_execute",
            "skillName": "gongkan_skill",
            "payload": {
                "taskId": "req:hybrid:2",
                "stepId": "zhgk.step1.hybrid",
                "goal": "读取 workspace 事实并总结",
                "allowedTools": ["read_file"],
                "maxIterations": 2,
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:runtime",
                "summaryNodeId": "summary-text",
            },
        },
        thread_id="t-run",
        agent_loop=_FakeAgentLoop(),
    )
    assert out.get("ok") is True
    assert out.get("subtaskOk") is True
    assert len(task_payloads) >= 2, "running + success terminal task status"
    assert task_payloads[0]["modules"][0]["status"] == "running"
    assert task_payloads[-1]["modules"][0]["status"] == "completed"
    assert patch_payloads, "expected SkillUiDataPatch"
    inner = patch_payloads[0].get("patch") if isinstance(patch_payloads[0], dict) else None
    assert isinstance(inner, dict)
    ops = inner.get("ops")
    assert isinstance(ops, list) and ops
    assert ops[0].get("op") == "merge"


@pytest.mark.asyncio
async def test_skill_agent_task_execute_failed_terminal_status(monkeypatch: pytest.MonkeyPatch) -> None:
    task_payloads: list[dict[str, Any]] = []

    async def capture_task_status(payload: dict[str, Any]) -> None:
        task_payloads.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_task_status_event", capture_task_status)

    async def _noop_skill_patch(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", _noop_skill_patch)

    async def fake_run_hybrid(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "error": "boom", "text": ""}

    monkeypatch.setattr("nanobot.web.hybrid_agent_subtask.run_hybrid_agent_subtask", fake_run_hybrid)

    class _FakeAgentLoop:
        provider = object()
        model = "fake-model"
        workspace = __import__("pathlib").Path("/tmp")
        restrict_to_workspace = False

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    out = await emit_skill_runtime_event(
        envelope={
            "event": "skill.agent_task_execute",
            "skillName": "gongkan_skill",
            "payload": {
                "taskId": "req:hybrid:fail",
                "stepId": "zhgk.step1.hybrid",
                "goal": "会失败",
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:runtime",
            },
        },
        thread_id="t-fail",
        agent_loop=_FakeAgentLoop(),
    )
    assert out.get("ok") is True
    assert out.get("subtaskOk") is False
    terminal = task_payloads[-1]["modules"][0]
    assert terminal["status"] == "failed"


@pytest.mark.asyncio
async def test_hybrid_agent_subtask_always_restricts_to_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from nanobot.providers.base import LLMResponse
    from nanobot.web import hybrid_agent_subtask as hmod

    captured: dict[str, Any] = {}
    real_build = hmod._build_tool_registry

    def spy_build(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(hmod, "_build_tool_registry", spy_build)

    class _P:
        async def chat_with_retry(self, **_k: Any) -> LLMResponse:
            return LLMResponse(content="仅验证沙箱参数")

    class _Loop:
        provider = _P()
        model = "m"
        workspace = Path("/tmp/nanobot-hybrid-sandbox-test")
        restrict_to_workspace = False

    await hmod.run_hybrid_agent_subtask(
        agent_loop=_Loop(),
        goal="noop",
        allowed_tools=["read_file"],
        max_iterations=1,
    )
    assert captured.get("restrict_to_workspace") is True
    assert captured.get("workspace") == Path("/tmp/nanobot-hybrid-sandbox-test")
