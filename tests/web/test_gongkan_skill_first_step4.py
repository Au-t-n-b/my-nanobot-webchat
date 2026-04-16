"""Integration-ish test: gongkan skill-first Step4 chain via driver + runtime bridge."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_gongkan_skill_first_step4_sends_approval_then_choice_then_distribute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "gongkan_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# gongkan\n", encoding="utf-8")
    (skill_dir / "runtime").mkdir(parents=True, exist_ok=True)
    (skill_dir / "data").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Start").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Input").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "RunTime").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Output").mkdir(parents=True, exist_ok=True)

    (skill_dir / "path_config.py").write_text(
        "\n".join(
            [
                "import os",
                "BASE = os.path.dirname(os.path.abspath(__file__))",
                "DATA = os.path.join(BASE, 'ProjectData')",
                "START_DIR = os.path.join(DATA, 'Start')",
                "INPUT_DIR = os.path.join(DATA, 'Input')",
                "RUNTIME_DIR = os.path.join(DATA, 'RunTime')",
                "OUTPUT_DIR = os.path.join(DATA, 'Output')",
                "def ensure_dirs():",
                "    for d in [START_DIR, INPUT_DIR, RUNTIME_DIR, OUTPUT_DIR]:",
                "        os.makedirs(d, exist_ok=True)",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # Required outputs for Step4
    out_dir = skill_dir / "ProjectData" / "Output"
    for name in ["工勘报告.docx", "全量勘测结果表.xlsx", "机房满足度评估表.xlsx", "风险识别结果表.xlsx"]:
        (out_dir / name).write_bytes(b"")

    # Fake distribute scripts
    scripts_dir = skill_dir / "zhgk" / "report-distribute" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "distribute_report.py").write_text("print('ok')\n", encoding="utf-8")
    (scripts_dir / "distribute_report_4b.py").write_text("print('ok')\n", encoding="utf-8")

    # Copy template driver/dashboard
    repo_root = Path(__file__).resolve().parents[2]
    (skill_dir / "runtime" / "driver.py").write_text(
        (repo_root / "templates" / "gongkan_skill" / "runtime" / "driver.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (skill_dir / "data" / "dashboard.json").write_text(
        (repo_root / "templates" / "gongkan_skill" / "data" / "dashboard.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()

    asked_choice: list[dict] = []
    patches: list[dict] = []

    async def fake_emit_patch(payload: dict):
        patches.append(payload)

    async def fake_emit_choices(self, title: str, options: list[dict], *, card_id: str | None = None, **kwargs):
        asked_choice.append({"card_id": card_id, "title": title, "options": options, **kwargs})
        from nanobot.web.mission_control import ChatCardHandle

        return ChatCardHandle(card_id=str(card_id or "card"), doc_id="chat:t-1")

    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", fake_emit_patch)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.emit_choices", fake_emit_choices)

    runner = make_skill_first_resume_runner(pending_hitl_store=store, python_executable=sys.executable)

    # 1) Send for approval => should emit choice request and persist pending
    out1 = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-4",
        action="zhgk_step4_send_for_approval",
        status="ok",
        result={},
    )
    assert out1["ok"] is True
    assert asked_choice
    pending = await store.get_pending_request("req-4:step4_approval_decision")
    assert pending is not None

    # 2) Handle approval pass => should complete distribution
    out2 = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-4",
        action="zhgk_step4_handle_approval",
        status="ok",
        result={"value": "approval_pass"},
    )
    assert out2["ok"] is True
    assert patches

