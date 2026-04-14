"""Fast-path tests for declarative skill manifest HITL bridging."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app
from nanobot.web.mission_control import ChatCardHandle


@pytest.fixture()
def local_tmp_dir() -> Path:
    root = Path(__file__).resolve().parents[2] / ".tmp" / "pytest-skill-manifest-fastpath"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"case-{uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _first_sse_data(body: str, event_name: str) -> dict | None:
    blocks = body.split("\n\n")
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        ev = None
        data_line = None
        for ln in lines:
            if ln.startswith("event:"):
                ev = ln[len("event:") :].strip()
            elif ln.startswith("data:"):
                data_line = ln[len("data:") :].strip()
        if ev == event_name and data_line:
            return json.loads(data_line)
    return None


def _write_manifest_skill(
    skills_root: Path,
    *,
    skill_name: str,
    manifest: dict[str, object],
) -> Path:
    skill_dir = skills_root / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (skill_dir / "skill.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return skill_dir


@pytest.mark.asyncio
async def test_dispatch_skill_manifest_guide_emits_file_picker(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = local_tmp_dir / "skills"
    _write_manifest_skill(
        skills_root,
        skill_name="plan_progress",
        manifest={
            "version": 1,
            "entry": "prepare_inputs",
            "stateNamespace": "plan_progress",
            "steps": [
                {
                    "id": "prepare_inputs",
                    "type": "file_gate",
                    "title": "请补齐输入文件",
                    "files": [
                        {
                            "label": "到货表.xlsx",
                            "path": "workspace/skills/plan_progress/input/到货表.xlsx",
                            "match": "strict",
                        }
                    ],
                    "upload": {
                        "saveDir": "skills/plan_progress/input",
                        "multiple": True,
                        "accept": ".xlsx",
                    },
                    "next": "done",
                }
            ],
        },
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    captured: dict[str, object] = {}

    async def fake_ask_for_file(self, **kwargs):
        captured.update(kwargs)
        return ChatCardHandle(card_id="card-upload", doc_id="chat:t-manifest")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        fake_ask_for_file,
    )

    from nanobot.web.skill_manifest_bridge import dispatch_skill_manifest_intent

    handled, message = await dispatch_skill_manifest_intent(
        {
            "type": "chat_card_intent",
            "verb": "skill_manifest_action",
            "payload": {
                "skillName": "plan_progress",
                "action": "guide",
            },
        },
        thread_id="t-manifest",
        docman=None,
    )

    assert handled is True
    assert isinstance(message, str)
    assert captured["title"] == "请补齐输入文件"
    assert captured["save_relative_dir"] == "skills/plan_progress/input"
    assert captured["skill_name"] == "plan_progress"
    assert captured["step_id"] == "prepare_inputs"


@pytest.mark.asyncio
async def test_dispatch_skill_manifest_resume_emits_choice_card(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = local_tmp_dir
    skills_root = workspace_root / "skills"
    input_file = workspace_root / "skills" / "plan_progress" / "input" / "到货表.xlsx"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_text("ok", encoding="utf-8")
    _write_manifest_skill(
        skills_root,
        skill_name="plan_progress",
        manifest={
            "version": 1,
            "entry": "prepare_inputs",
            "stateNamespace": "plan_progress",
            "steps": [
                {
                    "id": "prepare_inputs",
                    "type": "file_gate",
                    "title": "请补齐输入文件",
                    "files": [
                        {
                            "label": "到货表.xlsx",
                            "path": "workspace/skills/plan_progress/input/到货表.xlsx",
                            "match": "strict",
                        }
                    ],
                    "upload": {
                        "saveDir": "skills/plan_progress/input",
                        "multiple": True,
                        "accept": ".xlsx",
                    },
                    "next": "choose_mode",
                },
                {
                    "id": "choose_mode",
                    "type": "choice_gate",
                    "title": "请选择执行模式",
                    "options": [
                        {"id": "standard", "label": "标准模式"},
                        {"id": "fast", "label": "快速模式"},
                    ],
                    "storeAs": "selected_mode",
                    "nextByChoice": {
                        "standard": "done_standard",
                        "fast": "done_fast",
                    },
                },
            ],
        },
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    captured: dict[str, object] = {}

    async def fake_emit_choices(self, title, options, **kwargs):
        captured["title"] = title
        captured["options"] = options
        captured.update(kwargs)
        return ChatCardHandle(card_id="card-choice", doc_id="chat:t-manifest")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_choices",
        fake_emit_choices,
    )

    from nanobot.web.skill_manifest_bridge import dispatch_skill_manifest_intent

    handled, message = await dispatch_skill_manifest_intent(
        {
            "type": "chat_card_intent",
            "verb": "skill_manifest_action",
            "payload": {
                "skillName": "plan_progress",
                "action": "resume",
                "stepId": "prepare_inputs",
            },
        },
        thread_id="t-manifest",
        docman=None,
    )

    assert handled is True
    assert isinstance(message, str)
    assert captured["title"] == "请选择执行模式"
    assert len(captured["options"]) == 2
    assert captured["skill_name"] == "plan_progress"
    assert captured["step_id"] == "choose_mode"


@pytest.mark.asyncio
async def test_dispatch_skill_manifest_auto_executes_fixed_action_when_files_ready(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = local_tmp_dir
    skills_root = workspace_root / "skills"
    skill_dir = skills_root / "plan_progress" / "input"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "到货表.xlsx").write_text("ok", encoding="utf-8")
    (skill_dir / "人员信息表.xlsx").write_text("ok", encoding="utf-8")
    _write_manifest_skill(
        skills_root,
        skill_name="plan_progress",
        manifest={
            "version": 1,
            "entry": "prepare_inputs",
            "stateNamespace": "plan_progress",
            "steps": [
                {
                    "id": "prepare_inputs",
                    "type": "file_gate",
                    "title": "请补齐输入文件",
                    "files": [
                        {
                            "label": "到货表.xlsx",
                            "path": "workspace/skills/plan_progress/input/到货表.xlsx",
                            "match": "strict",
                        },
                        {
                            "label": "人员信息表.xlsx",
                            "path": "workspace/skills/plan_progress/input/人员信息表.xlsx",
                            "match": "strict",
                        },
                    ],
                    "upload": {
                        "saveDir": "skills/plan_progress/input",
                        "multiple": True,
                        "accept": ".xlsx",
                    },
                    "next": "execute_fixed_action",
                },
                {
                    "id": "execute_fixed_action",
                    "type": "fixed_action",
                    "title": "固定动作执行",
                    "message": "两个文件已齐全，已自动进入固定动作。",
                    "statePatch": {"all_inputs_ready": True},
                },
            ],
        },
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    from nanobot.web.skill_manifest_bridge import dispatch_skill_manifest_intent

    handled, message = await dispatch_skill_manifest_intent(
        {
            "type": "chat_card_intent",
            "verb": "skill_manifest_action",
            "payload": {
                "skillName": "plan_progress",
                "action": "guide",
            },
        },
        thread_id="t-manifest",
        docman=None,
    )

    assert handled is True
    assert message == "两个文件已齐全，已自动进入固定动作。"


@pytest.mark.asyncio
async def test_chat_skill_manifest_fastpath_skips_process_direct(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = local_tmp_dir / "skills"
    _write_manifest_skill(
        skills_root,
        skill_name="plan_progress",
        manifest={
            "version": 1,
            "entry": "prepare_inputs",
            "stateNamespace": "plan_progress",
            "steps": [
                {
                    "id": "prepare_inputs",
                    "type": "file_gate",
                    "title": "请补齐输入文件",
                    "files": [
                        {
                            "label": "到货表.xlsx",
                            "path": "workspace/skills/plan_progress/input/到货表.xlsx",
                            "match": "strict",
                        }
                    ],
                    "upload": {
                        "saveDir": "skills/plan_progress/input",
                        "multiple": True,
                        "accept": ".xlsx",
                    },
                    "next": "done",
                }
            ],
        },
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    async def fake_ask_for_file(self, **kwargs):
        return ChatCardHandle(card_id="card-upload", doc_id="chat:t-fastpath")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        fake_ask_for_file,
    )

    agent = MagicMock()
    agent.model = "m1"
    agent.process_direct = AsyncMock(return_value=type("Out", (), {"content": "fallback"})())
    agent.close_mcp = AsyncMock()

    app = create_app(agent_loop=agent)
    intent = {
        "type": "chat_card_intent",
        "verb": "skill_manifest_action",
        "payload": {
            "skillName": "plan_progress",
            "action": "guide",
        },
    }
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t-fastpath",
                "runId": "r-fastpath",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()
    fin = _first_sse_data(body, "RunFinished")
    assert fin is not None
    assert "error" not in fin
    agent.process_direct.assert_not_called()
