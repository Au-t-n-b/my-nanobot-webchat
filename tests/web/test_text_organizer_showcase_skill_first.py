"""Integration-ish test: text_organizer_showcase covers HITL + SDUI + artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_text_organizer_showcase_full_chain_file_choice_confirm_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "text_organizer_showcase"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "runtime").mkdir(parents=True, exist_ok=True)
    (skill_dir / "data").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Input").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Output").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    (skill_dir / "runtime" / "driver.py").write_text(
        (repo_root / "templates" / "text_organizer_showcase" / "runtime" / "driver.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (skill_dir / "data" / "dashboard.json").write_text(
        (repo_root / "templates" / "text_organizer_showcase" / "data" / "dashboard.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()

    asked_files: list[dict] = []
    asked_choices: list[dict] = []
    asked_confirms: list[dict] = []
    patches: list[dict] = []
    artifacts: list[dict] = []

    async def fake_ask_for_file(self, **kwargs):
        asked_files.append(kwargs)
        from nanobot.web.mission_control import ChatCardHandle

        return ChatCardHandle(card_id=str(kwargs.get("card_id") or "card"), doc_id="chat:t-1")

    async def fake_emit_choices(self, title, options, **kwargs):
        asked_choices.append({"title": title, "options": options, **kwargs})
        from nanobot.web.mission_control import ChatCardHandle

        return ChatCardHandle(card_id=str(kwargs.get("card_id") or "card"), doc_id="chat:t-1")

    async def fake_emit_confirm(self, title, **kwargs):
        asked_confirms.append({"title": title, **kwargs})
        from nanobot.web.mission_control import ChatCardHandle

        return ChatCardHandle(card_id=str(kwargs.get("card_id") or "card"), doc_id="chat:t-1")

    async def fake_emit_patch(payload: dict):
        patches.append(payload)

    async def fake_add_artifact(self, synthetic_path, *, doc_id, **kwargs):
        artifacts.append({"synthetic_path": synthetic_path, "doc_id": doc_id, **kwargs})

    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.ask_for_file", fake_ask_for_file)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.emit_choices", fake_emit_choices)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.emit_confirm", fake_emit_confirm)
    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", fake_emit_patch)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.add_artifact", fake_add_artifact)

    runner = make_skill_first_resume_runner(pending_hitl_store=store, python_executable=sys.executable)

    # 1) Start => ask for file upload (pending)
    out1 = await runner(
        thread_id="t-1",
        skill_name="text_organizer_showcase",
        request_id="req-demo",
        action="txo_step1_collect_inputs",
        status="ok",
        result={},
    )
    assert out1["ok"] is True
    assert asked_files
    pending1 = await store.get_pending_request("req-demo:step1_upload_inputs")
    assert pending1 is not None

    # Simulate platform saved an input file.
    (skill_dir / "ProjectData" / "Input" / "a.txt").write_text("hello", encoding="utf-8")

    # 2) Resume => should ask for choice (pending)
    out2 = await runner(
        thread_id="t-1",
        skill_name="text_organizer_showcase",
        request_id="req-demo",
        action="txo_step1_collect_inputs",
        status="ok",
        result={"files": [{"name": "a.txt", "uri": "workspace/skills/text_organizer_showcase/ProjectData/Input/a.txt"}]},
    )
    assert out2["ok"] is True
    assert asked_choices
    pending2 = await store.get_pending_request("req-demo:step2_choose_format")
    assert pending2 is not None

    # 3) Choice => confirm (pending)
    out3 = await runner(
        thread_id="t-1",
        skill_name="text_organizer_showcase",
        request_id="req-demo",
        action="txo_step3_confirm_and_run",
        status="ok",
        result={"value": "summary"},
    )
    assert out3["ok"] is True
    assert asked_confirms
    pending3 = await store.get_pending_request("req-demo:step3_confirm_run")
    assert pending3 is not None

    # 4) Confirm => publish artifact
    out4 = await runner(
        thread_id="t-1",
        skill_name="text_organizer_showcase",
        request_id="req-demo",
        action="txo_step4_publish",
        status="ok",
        result={"state": {"format": "summary"}},
    )
    assert out4["ok"] is True
    assert patches
    assert artifacts

