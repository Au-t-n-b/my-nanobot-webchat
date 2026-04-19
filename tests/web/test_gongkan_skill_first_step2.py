"""Integration-ish test: gongkan skill-first Step2 chain via driver + runtime bridge."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_gongkan_skill_first_step2_requests_upload_then_runs_and_publishes_artifacts(
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

    # Fake Step2 script: write skill_result.json + output artifacts.
    (skill_dir / "zhgk" / "survey-build" / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "zhgk" / "survey-build" / "scripts" / "generate_survey_table.py").write_text(
        "\n".join(
            [
                "import json, os, sys",
                "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))",
                "from path_config import OUTPUT_DIR, ensure_dirs",
                "ensure_dirs()",
                "for name in ['全量勘测结果表.xlsx','待客户确认勘测项.xlsx','待拍摄图片项.xlsx','待补充勘测项.xlsx']:",
                "  open(os.path.join(OUTPUT_DIR, name), 'wb').close()",
                "payload = {",
                "  'schema_version': '1.0',",
                "  'skill_name': 'zhgk',",
                "  'survey': {",
                "    'total_items': 10,",
                "    'filled_items': 6,",
                "    'empty_by_type': {'client_confirm': 1, 'photo': 2, 'supplement': 1}",
                "  }",
                "}",
                "with open(os.path.join(OUTPUT_DIR, 'skill_result.json'), 'w', encoding='utf-8') as f:",
                "  json.dump(payload, f, ensure_ascii=False, indent=2)",
                "print('ok')",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

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

    asked: list[dict] = []
    patches: list[dict] = []
    artifacts: list[dict] = []

    async def fake_ask_for_file(self, **kwargs):
        asked.append(kwargs)
        from nanobot.web.mission_control import ChatCardHandle

        return ChatCardHandle(card_id=str(kwargs.get("card_id") or "card"), doc_id="chat:t-1")

    async def fake_emit_patch(payload: dict):
        patches.append(payload)

    async def fake_add_artifact(self, doc_id, *, synthetic_path, **kwargs):
        artifacts.append({"synthetic_path": synthetic_path, "doc_id": doc_id, **kwargs})

    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.ask_for_file", fake_ask_for_file)
    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", fake_emit_patch)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.add_artifact", fake_add_artifact)

    runner = make_skill_first_resume_runner(pending_hitl_store=store, python_executable=sys.executable)

    # 1) Missing prerequisites => ask upload
    out1 = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-2",
        action="zhgk_step2_survey_build",
        status="ok",
        result={},
    )
    assert out1["ok"] is True
    assert asked
    pending = await store.get_pending_request("req-2:step2_upload_inputs")
    assert pending is not None

    # 2) Provide required files in directories
    runtime_dir = skill_dir / "ProjectData" / "RunTime"
    (runtime_dir / "勘测问题底表_过滤.xlsx").write_bytes(b"")
    input_dir = skill_dir / "ProjectData" / "Input"
    (input_dir / "勘测结果.xlsx").write_bytes(b"")

    out2 = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-2",
        action="zhgk_step2_survey_build",
        status="ok",
        result={"files": [{"name": "勘测结果.xlsx", "uri": "workspace/skills/gongkan_skill/ProjectData/Input/勘测结果.xlsx"}]},
    )
    assert out2["ok"] is True
    assert patches
    assert artifacts

