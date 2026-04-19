"""Integration-ish test: gongkan skill-first Step1 chain via driver + runtime bridge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_gongkan_skill_first_step1_requests_upload_then_patches_dashboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange a temp skills root with gongkan_skill runtime driver + dashboard.json
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "gongkan_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# gongkan\n", encoding="utf-8")
    (skill_dir / "runtime").mkdir(parents=True, exist_ok=True)
    (skill_dir / "data").mkdir(parents=True, exist_ok=True)
    # Minimal path_config + data dirs required by the template driver.
    (skill_dir / "ProjectData" / "Start").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Input").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "RunTime").mkdir(parents=True, exist_ok=True)
    (skill_dir / "ProjectData" / "Output").mkdir(parents=True, exist_ok=True)
    # Start/ required base tables must exist (driver treats them as delivery preinstall).
    start_dir = skill_dir / "ProjectData" / "Start"
    for name in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]:
        (start_dir / name).write_bytes(b"")

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

    # Fake Step1 script that writes skill_result.json + a runtime artifact.
    (skill_dir / "zhgk" / "scene-filter" / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "zhgk" / "scene-filter" / "scripts" / "scene_filter.py").write_text(
        "\n".join(
            [
                "import json, os, sys",
                "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))",
                "from path_config import OUTPUT_DIR, RUNTIME_DIR, ensure_dirs",
                "ensure_dirs()",
                "os.makedirs(RUNTIME_DIR, exist_ok=True)",
                "open(os.path.join(RUNTIME_DIR, '勘测问题底表_过滤.xlsx'), 'wb').close()",
                "payload = {",
                "  'schema_version': '1.0',",
                "  'skill_name': 'zhgk',",
                "  'scene_filter': {",
                "    'cooling_tag': '液冷_A3_下接管',",
                "    'scenario': '新址新建',",
                "    'filter_summary': {'勘测问题底表_过滤.xlsx': 3}",
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

    # Reuse the repo template driver/dashboard for test (copy text).
    driver_src = (Path(__file__).resolve().parents[2] / "templates" / "gongkan_skill" / "runtime" / "driver.py").read_text(
        encoding="utf-8"
    )
    dash_src = (Path(__file__).resolve().parents[2] / "templates" / "gongkan_skill" / "data" / "dashboard.json").read_text(
        encoding="utf-8"
    )
    (skill_dir / "runtime" / "driver.py").write_text(driver_src, encoding="utf-8")
    (skill_dir / "data" / "dashboard.json").write_text(dash_src, encoding="utf-8")

    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_resume_runner import make_skill_first_resume_runner

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()

    asked: list[dict] = []
    patches: list[dict] = []
    artifacts: list[dict] = []
    bootstraps: list[dict] = []
    envelopes: list[dict | None] = []

    async def fake_ask_for_file(self, **kwargs):
        asked.append(kwargs)
        # minimal handle shape
        from nanobot.web.mission_control import ChatCardHandle

        return ChatCardHandle(card_id=str(kwargs.get("card_id") or "card"), doc_id="chat:t-1")

    async def fake_emit_patch(payload: dict):
        patches.append(payload)

    async def fake_emit_bootstrap(payload: dict):
        bootstraps.append(payload)

    async def fake_add_artifact(self, doc_id, *, synthetic_path, **kwargs):
        artifacts.append({"synthetic_path": synthetic_path, "doc_id": doc_id, **kwargs})

    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.ask_for_file", fake_ask_for_file)
    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", fake_emit_patch)
    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_bootstrap_event", fake_emit_bootstrap)
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.add_artifact", fake_add_artifact)

    import nanobot.web.skill_resume_runner as resume_mod

    _orig_emit = resume_mod.emit_skill_runtime_event

    async def _trace_emit_skill_runtime_event(**kwargs):
        envelopes.append(kwargs.get("envelope"))
        return await _orig_emit(**kwargs)

    monkeypatch.setattr(resume_mod, "emit_skill_runtime_event", _trace_emit_skill_runtime_event)

    runner = make_skill_first_resume_runner(pending_hitl_store=store, python_executable=sys.executable)

    # 1) First resume with no files => should ask for upload and persist pending.
    out1 = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-0",
        action="start",
        status="ok",
        result={},  # no files
    )
    assert out1["ok"] is True
    assert asked, "expected hitl.file_request to render FilePicker"
    assert bootstraps, "expected dashboard.bootstrap -> emit_skill_ui_bootstrap_event"
    assert any("golden-metrics" in json.dumps(b, ensure_ascii=False) for b in bootstraps)

    # pending requestId is req-0:step1_upload_inputs per template driver
    pending = await store.get_pending_request("req-0:step1_upload_inputs")
    assert pending is not None
    assert pending["status"] == "pending"

    # 2) Second resume with uploaded files => should patch dashboard + publish artifacts.
    # Simulate platform saving the required files into ProjectData/Input.
    input_dir = skill_dir / "ProjectData" / "Input"
    (input_dir / "BOQ_test.xlsx").write_bytes(b"")
    (input_dir / "勘测信息预置集.docx").write_bytes(b"")
    out2 = await runner(
        thread_id="t-1",
        skill_name="gongkan_skill",
        request_id="req-0",
        action="zhgk_step1_scene_filter",
        status="ok",
        result={"files": [{"name": "BOQ_test.xlsx", "uri": "workspace/skills/gongkan_skill/ProjectData/Input/BOQ_test.xlsx"}]},
    )
    assert out2["ok"] is True
    assert patches, "expected dashboard.patch emission"
    assert artifacts, "expected artifact.publish -> add_artifact calls"

    assert any(
        isinstance(e, dict) and e.get("event") == "dashboard.bootstrap" for e in envelopes if e is not None
    )
    assert any(
        isinstance(e, dict)
        and e.get("event") == "dashboard.patch"
        and "golden-metrics" in json.dumps(e, ensure_ascii=False)
        and "chart-donut" in json.dumps(e, ensure_ascii=False)
        and "chart-bar" in json.dumps(e, ensure_ascii=False)
        for e in envelopes
        if e is not None
    )
    ack_ids = [
        (e.get("payload") or {}).get("cardId")
        for e in envelopes
        if isinstance(e, dict) and e.get("event") == "chat.guidance"
    ]
    assert "zhgk:ack:step1:inputs-ready" in ack_ids

