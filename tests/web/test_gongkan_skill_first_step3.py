"""Integration-ish test: gongkan skill-first Step3 chain via driver + runtime bridge."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_gongkan_skill_first_step3_runs_three_scripts_and_publishes_outputs(
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

    # Prerequisites
    output_dir = skill_dir / "ProjectData" / "Output"
    runtime_dir = skill_dir / "ProjectData" / "RunTime"
    start_dir = skill_dir / "ProjectData" / "Start"
    (output_dir / "全量勘测结果表.xlsx").write_bytes(b"")
    (runtime_dir / "评估项底表_过滤.xlsx").write_bytes(b"")
    (runtime_dir / "工勘常见高风险库_过滤.xlsx").write_bytes(b"")
    (runtime_dir / "project_info.json").write_text("{}", encoding="utf-8")
    (start_dir / "新版项目工勘报告模板.docx").write_bytes(b"")

    # Fake Step3 scripts that produce outputs
    (skill_dir / "zhgk" / "report-gen" / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "zhgk" / "report-gen" / "scripts" / "generate_assessment.py").write_text(
        "import os,sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))\n"
        "from path_config import OUTPUT_DIR, ensure_dirs\n"
        "ensure_dirs()\n"
        "open(os.path.join(OUTPUT_DIR,'机房满足度评估表.xlsx'),'wb').close()\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    (skill_dir / "zhgk" / "report-gen" / "scripts" / "generate_risk.py").write_text(
        "import os,sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))\n"
        "from path_config import OUTPUT_DIR, ensure_dirs\n"
        "ensure_dirs()\n"
        "open(os.path.join(OUTPUT_DIR,'风险识别结果表.xlsx'),'wb').close()\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    (skill_dir / "zhgk" / "report-gen" / "scripts" / "generate_report.py").write_text(
        "import json,os,sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))\n"
        "from path_config import OUTPUT_DIR, ensure_dirs\n"
        "ensure_dirs()\n"
        "open(os.path.join(OUTPUT_DIR,'工勘报告.docx'),'wb').close()\n"
        "open(os.path.join(OUTPUT_DIR,'整改待办.xlsx'),'wb').close()\n"
        "with open(os.path.join(OUTPUT_DIR,'skill_result.json'),'w',encoding='utf-8') as f:\n"
        "  json.dump({'schema_version':'1.0','skill_name':'zhgk','report':{'generated':True}}, f, ensure_ascii=False)\n"
        "print('ok')\n",
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

    patches: list[dict] = []
    artifacts: list[dict] = []

    async def fake_emit_patch(payload: dict):
        patches.append(payload)

    async def fake_add_artifact(self, synthetic_path, *, doc_id, **kwargs):
        artifacts.append({"synthetic_path": synthetic_path, "doc_id": doc_id, **kwargs})

    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", fake_emit_patch)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.add_artifact", fake_add_artifact)

    runner = make_skill_first_resume_runner(pending_hitl_store=store, python_executable=sys.executable)
    out = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-3",
        action="zhgk_step3_report_gen",
        status="ok",
        result={},
    )
    assert out["ok"] is True
    assert patches
    assert artifacts

