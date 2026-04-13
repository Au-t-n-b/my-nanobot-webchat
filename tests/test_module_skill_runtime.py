"""模块 Skill 运行时与 Fast-path 解析测试。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from nanobot.web.mission_control import ChatCardHandle


def _merge_node_ids_from_patch_payloads(payloads: list[dict]) -> set[str]:
    ids: set[str] = set()
    for p in payloads:
        patch = p.get("patch") if isinstance(p, dict) else None
        if not isinstance(patch, dict):
            continue
        for op in patch.get("ops") or []:
            if not isinstance(op, dict) or op.get("op") != "merge":
                continue
            tgt = op.get("target")
            if isinstance(tgt, dict):
                nid = str(tgt.get("nodeId") or "").strip()
                if nid:
                    ids.add(nid)
    return ids


def _append_ops_from_patch_payloads(payloads: list[dict]) -> list[dict]:
    out: list[dict] = []
    for p in payloads:
        patch = p.get("patch") if isinstance(p, dict) else None
        if not isinstance(patch, dict):
            continue
        for op in patch.get("ops") or []:
            if isinstance(op, dict) and op.get("op") == "append":
                out.append(op)
    return out


def _merge_values_for_node(payloads: list[dict], node_id: str) -> list[dict]:
    values: list[dict] = []
    for payload in payloads:
        patch = payload.get("patch") if isinstance(payload, dict) else None
        if not isinstance(patch, dict):
            continue
        for op in patch.get("ops") or []:
            if not isinstance(op, dict) or op.get("op") != "merge":
                continue
            target = op.get("target")
            if not isinstance(target, dict):
                continue
            if str(target.get("nodeId") or "").strip() != node_id:
                continue
            value = op.get("value")
            if isinstance(value, dict):
                values.append(value)
    return values


def _find_node_by_id(document: dict, node_id: str) -> dict | None:
    found: dict | None = None

    def walk(node: object) -> None:
        nonlocal found
        if found is not None:
            return
        if isinstance(node, dict):
            if str(node.get("id") or "").strip() == node_id:
                found = node
                return
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return found


def _expected_boilerplate_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=workspace/skills/module_boilerplate/data/dashboard.json"

def _expected_workbench_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/intelligent_analysis_workbench/data/dashboard.json"


def _expected_modeling_simulation_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/modeling_simulation_workbench/data/dashboard.json"


def _expected_job_management_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/job_management/data/dashboard.json"


def _expected_smart_survey_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/smart_survey_workbench/data/dashboard.json"


@pytest.fixture()
def capture_skill_ui_patches(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """收集 run_module_action 期间发出的 SkillUiDataPatch payload（绕过无 SSE 时的 no-op）。"""
    payloads: list[dict] = []

    async def capture(payload: dict) -> None:
        payloads.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", capture)
    return payloads


@pytest.fixture()
def capture_task_status_updates(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    payloads: list[dict] = []

    async def capture(payload: dict) -> None:
        payloads.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_task_status_event", capture)
    return payloads


@pytest.fixture()
def skills_module_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "skills"
    mod = root / "module_skill_demo"
    mod.mkdir(parents=True)
    (mod / "data").mkdir()
    (mod / "module.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "moduleId": "module_skill_demo",
                "docId": "dashboard:test-demo",
                "dataFile": "workspace/skills/module_skill_demo/data/dashboard.json",
                "flow": "demo_compliance",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mod / "data" / "dashboard.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "type": "SduiDocument",
                "root": {
                    "type": "Stack",
                    "children": [
                        {"type": "Stepper", "id": "stepper-main", "steps": []},
                        {"type": "Text", "id": "summary-text", "content": "demo"},
                        {"type": "ArtifactGrid", "id": "uploaded-files", "artifacts": []},
                        {"type": "ArtifactGrid", "id": "artifacts", "artifacts": []},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))
    return mod


def test_try_parse_chat_card_intent_embedded_json() -> None:
    """消息在 JSON 前有分隔线等杂质时仍应命中 fast-path（勿误送 LLM）。"""
    from nanobot.web.routes import _try_parse_chat_card_intent

    raw = (
        "————————————————————————"
        '{"type":"chat_card_intent","verb":"module_action",'
        '"payload":{"moduleId":"module_boilerplate","action":"guide","state":{}}}'
    )
    got = _try_parse_chat_card_intent(raw)
    assert got is not None
    assert got.get("verb") == "module_action"
    assert got.get("payload", {}).get("moduleId") == "module_boilerplate"


def test_parse_module_action_payload() -> None:
    from nanobot.web.module_skill_runtime import parse_module_action_payload

    assert parse_module_action_payload(None) is None
    assert parse_module_action_payload({"moduleId": "", "action": "x"}) is None
    got = parse_module_action_payload(
        {"moduleId": "module_skill_demo", "action": "start", "state": {"a": 1}}
    )
    assert got is not None
    mid, act, st = got
    assert mid == "module_skill_demo"
    assert act == "start"
    assert st == {"a": 1}


@pytest.mark.asyncio
async def test_dispatch_chat_card_intent_ignores_plain_user_text() -> None:
    from nanobot.web.module_skill_runtime import dispatch_chat_card_intent

    handled, msg = await dispatch_chat_card_intent(None, thread_id="t1", docman=None)
    assert handled is False
    assert msg == ""


@pytest.mark.asyncio
async def test_run_module_action_requires_thread(skills_module_demo: Path) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="module_skill_demo",
        action="guide",
        state={},
        thread_id="",
        docman=None,
    )
    assert r.get("ok") is False
    assert "thread_id" in (r.get("error") or "").lower()


@pytest.mark.asyncio
async def test_run_module_action_guide_emits_without_crash(skills_module_demo: Path) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="module_skill_demo",
        action="guide",
        state={},
        thread_id="thread-unit-1",
        docman=None,
    )
    assert r.get("ok") is True


@pytest.fixture()
def skills_module_boilerplate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "module_boilerplate"
    dst_root = tmp_path / "skills"
    shutil.copytree(src, dst_root / "module_boilerplate")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root / "module_boilerplate"


@pytest.mark.asyncio
async def test_load_module_config_boilerplate(skills_module_boilerplate: Path) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    cfg = load_module_config("module_boilerplate")
    assert cfg.get("flow") == "module_boilerplate"
    assert cfg.get("docId") == "dashboard:module-boilerplate"


@pytest.mark.asyncio
async def test_run_module_action_boilerplate_guide(skills_module_boilerplate: Path) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="module_boilerplate",
        action="guide",
        state={},
        thread_id="thread-boilerplate-1",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "start"


@pytest.mark.asyncio
async def test_run_module_action_boilerplate_start_evidence_gate_when_input_empty(
    skills_module_boilerplate: Path,
) -> None:
    """flowOptions.requireEvidenceBeforeStrategy：input 为空时 start 只下发 FilePicker，不经由模型。"""
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="module_boilerplate",
        action="start",
        state={},
        thread_id="thread-boilerplate-gate",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "resume_after_evidence_gate"

    inp = skills_module_boilerplate / "input"
    inp.mkdir(exist_ok=True)
    (inp / "seed.txt").write_text("ok", encoding="utf-8")
    r2 = await run_module_action(
        module_id="module_boilerplate",
        action="start",
        state={},
        thread_id="thread-boilerplate-gate-2",
        docman=None,
    )
    assert r2.get("ok") is True
    assert r2.get("next") == "choose_strategy"


@pytest.mark.asyncio
async def test_boilerplate_guide_patches_stepper_charts_summary(
    skills_module_boilerplate: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    """guide 应对 stepper-main、黄金指标图、summary-text 发 merge Patch（与 dashboard.json id 一致）。"""
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="module_boilerplate",
        action="guide",
        state={},
        thread_id="thread-bp-patch-guide",
        docman=None,
    )
    assert r.get("ok") is True
    assert capture_skill_ui_patches, "应至少发出一条 SkillUiDataPatch"
    exp_sp = _expected_boilerplate_synthetic_path()
    for p in capture_skill_ui_patches:
        assert p.get("syntheticPath") == exp_sp
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert {"stepper-main", "chart-donut", "chart-bar", "summary-text"}.issubset(merged)


@pytest.mark.asyncio
async def test_boilerplate_start_patches_stepper_when_input_warmed(
    skills_module_boilerplate: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    """门禁关闭路径：input 已有文件时 start 应 Patch 进展与黄金指标。"""
    from nanobot.web.module_skill_runtime import run_module_action

    inp = skills_module_boilerplate / "input"
    inp.mkdir(exist_ok=True)
    (inp / "warm.txt").write_text("x", encoding="utf-8")

    r = await run_module_action(
        module_id="module_boilerplate",
        action="start",
        state={},
        thread_id="thread-bp-patch-start",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "choose_strategy"
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert "stepper-main" in merged
    assert "chart-donut" in merged
    assert "chart-bar" in merged


@pytest.mark.asyncio
async def test_boilerplate_start_evidence_gate_calls_ask_for_file(
    skills_module_boilerplate: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """requireEvidenceBeforeStrategy + 空 input：须调用 ask_for_file（真实 FilePicker 路径），并 Patch Stepper。"""
    from nanobot.web.module_skill_runtime import run_module_action

    mock_af = AsyncMock(
        return_value=ChatCardHandle(card_id="upload:test:1", doc_id="chat:thread-bp-gate-af")
    )
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        mock_af,
    )

    r = await run_module_action(
        module_id="module_boilerplate",
        action="start",
        state={},
        thread_id="thread-bp-gate-af",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "resume_after_evidence_gate"
    mock_af.assert_awaited_once()
    kwargs = mock_af.await_args.kwargs
    assert kwargs.get("next_action") == "resume_after_evidence_gate"
    assert kwargs.get("module_id") == "module_boilerplate"
    assert "save_relative_dir" in kwargs
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert "stepper-main" in merged


@pytest.mark.asyncio
async def test_boilerplate_finish_emits_artifact_append(
    skills_module_boilerplate: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    """finish 须追加产物：append op 目标为 artifacts（与前端 applySduiPatch 对齐）。"""
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="module_boilerplate",
        action="finish",
        state={"standard": "balanced"},
        thread_id="thread-bp-finish-art",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("done") is True
    appends = _append_ops_from_patch_payloads(capture_skill_ui_patches)
    assert appends, "finish 应发出至少一条 append Patch"
    art_ops = [
        o
        for o in appends
        if str((o.get("target") or {}).get("nodeId") or "") == "artifacts"
        and str((o.get("target") or {}).get("field") or "") == "artifacts"
    ]
    assert art_ops, "应有针对 ArtifactGrid.artifacts 的 append"
    val = art_ops[-1].get("value")
    assert isinstance(val, dict)
    assert val.get("id") == "boilerplate-report-001"
    assert val.get("kind") == "md"
    assert str(val.get("label") or "").endswith(".md")
    report = skills_module_boilerplate / "output" / "module_case_handover.md"
    assert report.is_file()


@pytest.mark.asyncio
async def test_boilerplate_uses_case_template_config(
    skills_module_boilerplate: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """module.json.caseTemplate 中的策略选项、指标名、交付文件名应能驱动样板行为。"""
    from nanobot.web.module_skill_runtime import load_module_config, run_module_action

    cfg = load_module_config("module_boilerplate")
    cfg["caseTemplate"] = {
        "moduleTitle": "站点交付模块",
        "moduleGoal": "演示站点交付模块的参考案例。",
        "strategyPrompt": "请选择站点交付策略：",
        "strategyOptions": [
            {"id": "safe", "label": "稳妥推进"},
            {"id": "fast", "label": "快速推进"},
        ],
        "metricLabels": {
            "throughput": "交付吞吐",
            "quality": "验收质量",
            "risk": "遗留风险",
        },
        "reportLabel": "站点交付说明.md",
        "reportFileName": "site_delivery_handover.md",
    }
    (skills_module_boilerplate / "module.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mock_choices = AsyncMock()
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_choices",
        mock_choices,
    )

    await run_module_action(
        module_id="module_boilerplate",
        action="choose_strategy",
        state={},
        thread_id="thread-bp-case-template",
        docman=None,
    )
    mock_choices.assert_awaited_once()
    kwargs = mock_choices.await_args.kwargs
    assert kwargs.get("title") == "请选择站点交付策略："
    assert kwargs.get("options") == [
        {"id": "safe", "label": "稳妥推进"},
        {"id": "fast", "label": "快速推进"},
    ]

    r = await run_module_action(
        module_id="module_boilerplate",
        action="finish",
        state={"standard": "safe"},
        thread_id="thread-bp-case-template",
        docman=None,
    )
    assert r.get("ok") is True
    report = skills_module_boilerplate / "output" / "site_delivery_handover.md"
    assert report.is_file()

@pytest.fixture()
def skills_intelligent_analysis_workbench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "intelligent_analysis_workbench"
    dst_root = tmp_path / "skills"
    shutil.copytree(src, dst_root / "intelligent_analysis_workbench")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root / "intelligent_analysis_workbench"


@pytest.fixture()
def skills_modeling_simulation_workbench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "modeling_simulation_workbench"
    dst_root = tmp_path / "skills"
    shutil.copytree(src, dst_root / "modeling_simulation_workbench")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root / "modeling_simulation_workbench"


@pytest.fixture()
def skills_smart_survey_workbench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "smart_survey_workbench"
    dst_root = tmp_path / "skills"
    shutil.copytree(src, dst_root / "smart_survey_workbench")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root / "smart_survey_workbench"


@pytest.fixture()
def skills_job_management_with_plan_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    dst_root = tmp_path / "skills"
    shutil.copytree(repo_root / "templates" / "job_management", dst_root / "job_management")
    plan_root = dst_root / "plan_progress"
    (plan_root / "input").mkdir(parents=True)
    (plan_root / "ProjectData" / "RunTime").mkdir(parents=True)
    (plan_root / "stage1_extracted").mkdir(parents=True)
    (plan_root / "stage2_decoupled" / "scripts").mkdir(parents=True)
    (plan_root / "stage3_extracted" / "milestone").mkdir(parents=True)
    (plan_root / "stage3_extracted" / "schedule").mkdir(parents=True)
    (plan_root / "stage3_extracted" / "reflection").mkdir(parents=True)
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root


@pytest.fixture()
def skills_smart_survey_with_gongkan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    dst_root = tmp_path / "skills"
    shutil.copytree(repo_root / "templates" / "smart_survey_workbench", dst_root / "smart_survey_workbench")
    gongkan = dst_root / "gongkan_skill"
    (gongkan / "ProjectData" / "Start").mkdir(parents=True)
    (gongkan / "ProjectData" / "Input").mkdir(parents=True)
    (gongkan / "ProjectData" / "Images").mkdir(parents=True)
    (gongkan / "ProjectData" / "Output").mkdir(parents=True)
    (gongkan / "ProjectData" / "RunTime").mkdir(parents=True)
    (gongkan / "ProjectData" / "RunTime" / "progress.json").write_text(
        json.dumps({"modules": [{"moduleId": "smart_survey", "tasks": []}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root


def test_load_module_config_rejects_missing_save_relative_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    root = tmp_path / "skills"
    module_dir = root / "bad_module"
    module_dir.mkdir(parents=True)
    (module_dir / "data").mkdir()
    (module_dir / "module.json").write_text(
        json.dumps(
            {
                "moduleId": "bad_module",
                "flow": "intelligent_analysis_workbench",
                "docId": "dashboard:bad-module",
                "dataFile": "skills/bad_module/data/dashboard.json",
                "uploads": [{"purpose": "bundle"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (module_dir / "data" / "dashboard.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "type": "SduiDocument",
                "root": {
                    "type": "Stack",
                    "children": [
                        {"type": "Stepper", "id": "stepper-main", "steps": []},
                        {"type": "Text", "id": "summary-text", "content": "x"},
                        {"type": "ArtifactGrid", "id": "artifacts", "artifacts": []},
                        {"type": "ArtifactGrid", "id": "uploaded-files", "artifacts": []},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    with pytest.raises(ValueError, match="save_relative_dir"):
        load_module_config("bad_module")


def test_load_module_config_rejects_missing_uploaded_files_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    root = tmp_path / "skills"
    module_dir = root / "bad_dashboard"
    module_dir.mkdir(parents=True)
    (module_dir / "data").mkdir()
    (module_dir / "module.json").write_text(
        json.dumps(
            {
                "moduleId": "bad_dashboard",
                "flow": "intelligent_analysis_workbench",
                "docId": "dashboard:bad-dashboard",
                "dataFile": "skills/bad_dashboard/data/dashboard.json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (module_dir / "data" / "dashboard.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "type": "SduiDocument",
                "root": {
                    "type": "Stack",
                    "children": [
                        {"type": "Stepper", "id": "stepper-main", "steps": []},
                        {"type": "Text", "id": "summary-text", "content": "x"},
                        {"type": "ArtifactGrid", "id": "artifacts", "artifacts": []},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    with pytest.raises(ValueError, match="uploaded-files"):
        load_module_config("bad_dashboard")


@pytest.mark.asyncio
async def test_load_module_config_intelligent_analysis_workbench(
    skills_intelligent_analysis_workbench: Path,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    cfg = load_module_config("intelligent_analysis_workbench")
    assert cfg.get("flow") == "intelligent_analysis_workbench"
    assert cfg.get("docId") == "dashboard:intelligent-analysis-workbench"


@pytest.mark.asyncio
async def test_intelligent_analysis_workbench_guide_emits_dashboard_nodes(
    skills_intelligent_analysis_workbench: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="intelligent_analysis_workbench",
        action="guide",
        state={},
        thread_id="thread-workbench-guide",
        docman=None,
    )
    assert r.get("ok") is True
    for payload in capture_skill_ui_patches:
        assert payload.get("syntheticPath") == _expected_workbench_synthetic_path()
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert {"stepper-main", "chart-donut", "chart-bar", "summary-text", "uploaded-files"}.issubset(merged)


@pytest.mark.asyncio
async def test_intelligent_analysis_workbench_parallel_phase_emits_task_status_updates(
    skills_intelligent_analysis_workbench: Path,
    capture_skill_ui_patches: list[dict],
    capture_task_status_updates: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="intelligent_analysis_workbench",
        action="run_parallel_skills",
        state={
            "standard": "comprehensive",
            "upload": {"name": "项目分析资料包.zip"},
        },
        thread_id="thread-workbench-parallel",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "synthesize_result"
    assert len(capture_skill_ui_patches) >= 2
    assert any((p.get("patch") or {}).get("isPartial") is True for p in capture_skill_ui_patches)
    assert capture_task_status_updates, "项目总览进展应随模块执行同步推送"
    latest = capture_task_status_updates[-1]
    modules = latest.get("modules")
    assert isinstance(modules, list)
    workbench = next((m for m in modules if m.get("name") == "智能分析工作台"), None)
    assert workbench is not None
    assert workbench.get("status") == "running"
    steps = workbench.get("steps")
    assert isinstance(steps, list)
    assert any(step.get("name") == "并行分析进行中" and step.get("done") is True for step in steps)


@pytest.mark.asyncio
async def test_intelligent_analysis_workbench_parallel_phase_syncs_uploaded_files(
    skills_intelligent_analysis_workbench: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    thread_id = "thread-workbench-upload-sync"
    r = await module_skill_runtime.run_module_action(
        module_id="intelligent_analysis_workbench",
        action="run_parallel_skills",
        state={
            "standard": "comprehensive",
            "upload": {
                "fileId": "file-001",
                "name": "项目分析资料包.zip",
                "logicalPath": "workspace/skills/intelligent_analysis_workbench/input/项目分析资料包.zip",
            },
            "uploads": [
                {
                    "fileId": "file-001",
                    "name": "项目分析资料包.zip",
                    "logicalPath": "workspace/skills/intelligent_analysis_workbench/input/项目分析资料包.zip",
                    "savedDir": "skills/intelligent_analysis_workbench/input",
                }
            ],
        },
        thread_id=thread_id,
        docman=None,
    )
    assert r.get("ok") is True
    merged = module_skill_runtime.merge_module_session(thread_id, "intelligent_analysis_workbench", {})
    uploads = merged.get("uploads")
    assert isinstance(uploads, list)
    assert uploads
    assert uploads[0].get("logicalPath") == "workspace/skills/intelligent_analysis_workbench/input/项目分析资料包.zip"

    uploaded_file_updates = _merge_values_for_node(capture_skill_ui_patches, "uploaded-files")
    assert uploaded_file_updates, "上传成功后应同步 patch 到 uploaded-files 节点"
    latest = uploaded_file_updates[-1]
    artifacts = latest.get("artifacts")
    assert isinstance(artifacts, list)
    assert artifacts
    assert artifacts[0].get("label") == "项目分析资料包.zip"
    assert artifacts[0].get("path") == "workspace/skills/intelligent_analysis_workbench/input/项目分析资料包.zip"


@pytest.mark.asyncio
async def test_intelligent_analysis_workbench_parallel_phase_replaces_chat_card_with_uploaded_capsules(
    skills_intelligent_analysis_workbench: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    captured: dict[str, object] = {}

    async def fake_replace_card(self, *, card_id: str, title: str, node: dict, doc_id: str | None = None):
        captured["card_id"] = card_id
        captured["title"] = title
        captured["node"] = node
        captured["doc_id"] = doc_id
        return ChatCardHandle(card_id=card_id, doc_id=str(doc_id or ""))

    monkeypatch.setattr(
        module_skill_runtime.MissionControlManager,
        "replace_card",
        fake_replace_card,
        raising=True,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="intelligent_analysis_workbench",
        action="run_parallel_skills",
        state={
            "cardId": "upload-card-001",
            "standard": "comprehensive",
            "upload": {
                "fileId": "file-002",
                "name": "项目分析资料包.zip",
                "logicalPath": "workspace/skills/intelligent_analysis_workbench/input/项目分析资料包.zip",
            },
            "uploads": [
                {
                    "fileId": "file-002",
                    "name": "项目分析资料包.zip",
                    "logicalPath": "workspace/skills/intelligent_analysis_workbench/input/项目分析资料包.zip",
                    "savedDir": "skills/intelligent_analysis_workbench/input",
                },
                {
                    "fileId": "file-003",
                    "name": "补充材料.pdf",
                    "logicalPath": "workspace/skills/intelligent_analysis_workbench/input/补充材料.pdf",
                    "savedDir": "skills/intelligent_analysis_workbench/input",
                },
            ],
        },
        thread_id="thread-workbench-upload-card",
        docman=None,
    )

    assert r.get("ok") is True
    assert captured.get("card_id") == "upload-card-001"
    assert captured.get("title") == "资料已上传"
    node = captured.get("node")
    assert isinstance(node, dict)
    children = node.get("children")
    assert isinstance(children, list)
    artifact_grid = next((child for child in children if isinstance(child, dict) and child.get("type") == "ArtifactGrid"), None)
    assert artifact_grid is not None, "聊天卡片应展示已上传文件胶囊区"
    artifacts = artifact_grid.get("artifacts")
    assert isinstance(artifacts, list)
    assert len(artifacts) == 2
    assert any(item.get("label") == "补充材料.pdf" for item in artifacts if isinstance(item, dict))


@pytest.mark.asyncio
async def test_intelligent_analysis_workbench_task_progress_uses_module_config(
    skills_intelligent_analysis_workbench: Path,
    capture_task_status_updates: list[dict],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from nanobot.config import loader as config_loader
    import nanobot.web.module_skill_runtime as module_skill_runtime

    config_path = tmp_path / ".nanobot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_loader, "_current_config_path", config_path)

    cfg = module_skill_runtime.load_module_config("intelligent_analysis_workbench")
    cfg["taskProgress"] = {
        "moduleId": "custom_analysis",
        "moduleName": "自定义分析模块",
        "tasks": ["阶段 A", "阶段 B", "阶段 C"],
        "actionMapping": {
            "guide": ["阶段 A"],
            "upload_bundle": ["阶段 A", "阶段 B"],
            "finish": ["阶段 A", "阶段 B", "阶段 C"],
        },
    }
    (skills_intelligent_analysis_workbench / "module.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    r = await module_skill_runtime.run_module_action(
        module_id="intelligent_analysis_workbench",
        action="upload_bundle",
        state={"standard": "comprehensive"},
        thread_id="thread-workbench-task-progress-config",
        docman=None,
    )
    assert r.get("ok") is True
    assert capture_task_status_updates
    latest = capture_task_status_updates[-1]
    modules = latest.get("modules")
    assert isinstance(modules, list)
    module = next((item for item in modules if item.get("name") == "自定义分析模块"), None)
    assert module is not None
    steps = module.get("steps")
    assert isinstance(steps, list)
    assert any(step.get("name") == "阶段 B" and step.get("done") is True for step in steps)
    assert any(step.get("name") == "阶段 C" and step.get("done") is False for step in steps)


@pytest.mark.asyncio
async def test_intelligent_analysis_workbench_finish_emits_completed_task_status(
    skills_intelligent_analysis_workbench: Path,
    capture_task_status_updates: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="intelligent_analysis_workbench",
        action="finish",
        state={
            "standard": "comprehensive",
            "upload": {"name": "项目分析资料包.zip"},
        },
        thread_id="thread-workbench-finish",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("done") is True
    assert capture_task_status_updates
    latest = capture_task_status_updates[-1]
    modules = latest.get("modules")
    assert isinstance(modules, list)
    workbench = next((m for m in modules if m.get("name") == "智能分析工作台"), None)
    assert workbench is not None
    assert workbench.get("status") == "completed"
    assert all(bool(step.get("done")) for step in workbench.get("steps") or [])


@pytest.mark.asyncio
async def test_load_module_config_modeling_simulation_workbench(
    skills_modeling_simulation_workbench: Path,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    cfg = load_module_config("modeling_simulation_workbench")
    assert cfg.get("flow") == "simulation_workflow"
    assert cfg.get("docId") == "dashboard:modeling-simulation-workbench"


@pytest.mark.asyncio
async def test_load_module_config_smart_survey_workbench(
    skills_smart_survey_workbench: Path,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    cfg = load_module_config("smart_survey_workbench")
    assert cfg.get("flow") == "smart_survey_workflow"
    assert cfg.get("docId") == "dashboard:smart-survey-workbench"


def test_load_module_config_normalizes_legacy_smart_survey_dashboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "smart_survey_workbench"
    skills_root = tmp_path / "skills"
    module_dir = skills_root / "smart_survey_workbench"
    shutil.copytree(src, module_dir)
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    legacy_dashboard = {
        "schemaVersion": 1,
        "type": "SduiDocument",
        "meta": {"docId": "dashboard:smart-survey-workbench", "provenance": "smart_survey_workbench"},
        "root": {
            "type": "Stack",
            "children": [
                {
                    "type": "Stepper",
                    "id": "stepper-main",
                    "steps": [
                        {"id": "s1", "title": "场景筛选与底表过滤", "status": "completed"},
                        {"id": "s4", "title": "审批分发", "status": "active"},
                    ],
                },
                {
                    "type": "Row",
                    "children": [
                        {"type": "DonutChart", "id": "chart-donut", "segments": []},
                        {
                            "type": "BarChart",
                            "id": "chart-bar",
                            "bars": [
                                {"label": "勘测完成度", "value": 75, "color": "#2196F3"},
                                {"label": "数据完整率", "value": 88, "color": "#FF9800"},
                            ],
                        },
                    ],
                },
                {"type": "Text", "id": "summary-text", "content": "legacy"},
                {
                    "type": "ArtifactGrid",
                    "id": "uploaded-files",
                    "artifacts": [{"name": "BOQ.xlsx", "status": "ready"}],
                },
                {
                    "type": "ArtifactGrid",
                    "id": "artifacts",
                    "artifacts": [{"name": "工勘报告.docx", "status": "ready"}],
                },
            ],
        },
    }
    dashboard_path = module_dir / "data" / "dashboard.json"
    dashboard_path.write_text(json.dumps(legacy_dashboard, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_module_config("smart_survey_workbench")

    assert cfg.get("flow") == "smart_survey_workflow"
    normalized = json.loads(dashboard_path.read_text(encoding="utf-8"))
    chart_bar = _find_node_by_id(normalized, "chart-bar")
    assert isinstance(chart_bar, dict)
    assert isinstance(chart_bar.get("data"), list)
    assert "bars" not in chart_bar
    uploaded = _find_node_by_id(normalized, "uploaded-files")
    assert isinstance(uploaded, dict)
    assert uploaded.get("artifacts") == []


@pytest.mark.asyncio
async def test_smart_survey_workbench_guide_emits_dashboard_nodes(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="smart_survey_workbench",
        action="guide",
        state={},
        thread_id="thread-smart-guide",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "prepare_step1"
    for payload in capture_skill_ui_patches:
        assert payload.get("syntheticPath") == _expected_smart_survey_synthetic_path()
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert {"stepper-main", "summary-text", "uploaded-files", "artifacts"}.issubset(merged)


@pytest.mark.asyncio
async def test_smart_survey_prepare_step1_requests_missing_inputs(
    skills_smart_survey_with_gongkan: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    mock_af = AsyncMock(
        return_value=ChatCardHandle(card_id="upload:smart:step1", doc_id="chat:thread-smart-step1")
    )
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        mock_af,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="prepare_step1",
        state={},
        thread_id="thread-smart-step1",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "run_step1"
    mock_af.assert_awaited_once()


@pytest.mark.asyncio
async def test_smart_survey_run_step1_updates_summary_and_artifacts(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    skill_root = skills_smart_survey_with_gongkan / "gongkan_skill"
    start_dir = skill_root / "ProjectData" / "Start"
    input_dir = skill_root / "ProjectData" / "Input"
    for name in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]:
        (start_dir / name).write_text(name, encoding="utf-8")
    (input_dir / "sample_BOQ.xlsx").write_text("boq", encoding="utf-8")
    (input_dir / "勘测信息预置集.docx").write_text("preset", encoding="utf-8")

    monkeypatch.setattr(
        module_skill_runtime,
        "_run_gongkan_step1",
        AsyncMock(
            return_value={
                "ok": True,
                "summary": "已识别液冷/A3/新址新建",
                "artifacts": [{"label": "定制工勘表.xlsx"}],
            }
        ),
        raising=False,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="run_step1",
        state={},
        thread_id="thread-smart-run1",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "prepare_step2"
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert summary_updates
    assert "液冷" in str(summary_updates[-1].get("content") or "")
    artifact_updates = _merge_values_for_node(capture_skill_ui_patches, "artifacts")
    assert artifact_updates


@pytest.mark.asyncio
async def test_smart_survey_prepare_step2_requests_missing_results_or_images(
    skills_smart_survey_with_gongkan: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    skill_root = skills_smart_survey_with_gongkan / "gongkan_skill"
    (skill_root / "ProjectData" / "RunTime" / "勘测问题底表_过滤.xlsx").write_text("filtered", encoding="utf-8")

    mock_af = AsyncMock(
        return_value=ChatCardHandle(card_id="upload:smart:step2", doc_id="chat:thread-smart-step2")
    )
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        mock_af,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="prepare_step2",
        state={},
        thread_id="thread-smart-step2",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "run_step2"
    mock_af.assert_awaited_once()


@pytest.mark.asyncio
async def test_smart_survey_run_step2_updates_uploaded_files_kpis_and_summary(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    monkeypatch.setattr(
        module_skill_runtime,
        "_run_gongkan_step2",
        AsyncMock(
            return_value={
                "ok": True,
                "summary": "已生成全量勘测结果表，完整率 81%",
                "uploaded_artifacts": [{"label": "勘测结果.xlsx"}],
                "artifacts": [{"label": "全量勘测结果表.xlsx"}],
                "metrics": {"completion": 81, "integrity": 81, "remaining": 24},
            }
        ),
        raising=False,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="run_step2",
        state={},
        thread_id="thread-smart-run2",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "prepare_step3"
    uploaded_updates = _merge_values_for_node(capture_skill_ui_patches, "uploaded-files")
    assert uploaded_updates
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert "完整率" in str(summary_updates[-1].get("content") or "")


@pytest.mark.asyncio
async def test_smart_survey_run_step4_approve_pauses_before_finish(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    emit_guidance = AsyncMock()
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_guidance",
        emit_guidance,
    )
    monkeypatch.setattr(
        module_skill_runtime,
        "_run_gongkan_step4_approve",
        AsyncMock(return_value={"ok": True, "summary": "已发送专家审批，等待回执"}),
        raising=False,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="run_step4_approve",
        state={},
        thread_id="thread-smart-approve",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "approval_pass"
    emit_guidance.assert_awaited_once()
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert "等待回执" in str(summary_updates[-1].get("content") or "")


def test_system_prompt_mentions_smart_survey_workbench_flow() -> None:
    from nanobot.agent.context import ContextBuilder

    prompt = ContextBuilder(Path("D:/code/nanobot")).build_system_prompt([])
    assert "smart_survey_workbench" in prompt
    assert 'module_skill_runtime(module_id="smart_survey_workbench", action="prepare_step1"' in prompt
    assert "approval_pass" in prompt


@pytest.mark.asyncio
async def test_modeling_simulation_workbench_guide_emits_dashboard_nodes(
    skills_modeling_simulation_workbench: Path,
    capture_skill_ui_patches: list[dict],
    capture_task_status_updates: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="modeling_simulation_workbench",
        action="guide",
        state={},
        thread_id="thread-modeling-guide",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "upload_bundle"
    for payload in capture_skill_ui_patches:
        assert payload.get("syntheticPath") == _expected_modeling_simulation_synthetic_path()
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert {"stepper-main", "summary-text", "uploaded-files", "embedded-modeling-access"}.issubset(merged)
    assert capture_task_status_updates
    latest = capture_task_status_updates[-1]
    modules = latest.get("modules")
    assert isinstance(modules, list)
    modeling = next((m for m in modules if m.get("name") == "建模仿真模块"), None)
    assert modeling is not None


@pytest.mark.asyncio
async def test_modeling_simulation_workbench_upload_complete_advances_to_device_confirm(
    skills_modeling_simulation_workbench: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="modeling_simulation_workbench",
        action="upload_bundle_complete",
        state={
            "upload": {
                "fileId": "sim-file-001",
                "name": "simulation_boq_bundle.zip",
                "logicalPath": "workspace/skills/modeling_simulation_workbench/input/simulation_boq_bundle.zip",
            },
            "uploads": [
                {
                    "fileId": "sim-file-001",
                    "name": "simulation_boq_bundle.zip",
                    "logicalPath": "workspace/skills/modeling_simulation_workbench/input/simulation_boq_bundle.zip",
                    "savedDir": "skills/modeling_simulation_workbench/input",
                }
            ],
        },
        thread_id="thread-modeling-upload",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "device_confirm"
    uploaded_updates = _merge_values_for_node(capture_skill_ui_patches, "uploaded-files")
    assert uploaded_updates
    latest = uploaded_updates[-1]
    artifacts = latest.get("artifacts")
    assert isinstance(artifacts, list)
    assert artifacts
    assert artifacts[0].get("label") == "simulation_boq_bundle.zip"


@pytest.mark.asyncio
async def test_modeling_simulation_workbench_finish_emits_completed_task_status(
    skills_modeling_simulation_workbench: Path,
    capture_task_status_updates: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="modeling_simulation_workbench",
        action="finish",
        state={
            "upload": {"name": "simulation_boq_bundle.zip"},
            "uploads": [
                {
                    "fileId": "sim-file-001",
                    "name": "simulation_boq_bundle.zip",
                    "logicalPath": "workspace/skills/modeling_simulation_workbench/input/simulation_boq_bundle.zip",
                    "savedDir": "skills/modeling_simulation_workbench/input",
                }
            ],
        },
        thread_id="thread-modeling-finish",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("done") is True
    assert capture_task_status_updates
    latest = capture_task_status_updates[-1]
    modules = latest.get("modules")
    assert isinstance(modules, list)
    modeling = next((m for m in modules if m.get("name") == "建模仿真模块"), None)
    assert modeling is not None
    assert modeling.get("status") == "completed"
    assert all(bool(step.get("done")) for step in modeling.get("steps") or [])


@pytest.mark.asyncio
async def test_job_management_upload_bundle_requests_missing_required_files(
    skills_job_management_with_plan_progress: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    mock_af = AsyncMock(
        return_value=ChatCardHandle(card_id="upload:job:required", doc_id="chat:thread-job-missing")
    )
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        mock_af,
    )

    r = await module_skill_runtime.run_module_action(
        module_id="job_management",
        action="upload_bundle",
        state={},
        thread_id="thread-job-missing",
        docman=None,
    )

    assert r.get("ok") is True
    assert r.get("next") == "upload_bundle_complete"
    mock_af.assert_awaited_once()
    kwargs = mock_af.await_args.kwargs
    assert kwargs.get("save_relative_dir") == "skills/plan_progress/input"
    assert kwargs.get("multiple") is True
    assert kwargs.get("accept") == ".xlsx"
    for payload in capture_skill_ui_patches:
        assert payload.get("syntheticPath") == _expected_job_management_synthetic_path()
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert summary_updates
    assert "到货表.xlsx" in str(summary_updates[-1].get("content") or "")
    assert "人员信息表.xlsx" in str(summary_updates[-1].get("content") or "")


@pytest.mark.asyncio
async def test_job_management_upload_bundle_complete_advances_when_required_inputs_present(
    skills_job_management_with_plan_progress: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    input_dir = skills_job_management_with_plan_progress / "plan_progress" / "input"
    (input_dir / "到货表.xlsx").write_text("arrival", encoding="utf-8")
    (input_dir / "人员信息表.xlsx").write_text("people", encoding="utf-8")

    r = await module_skill_runtime.run_module_action(
        module_id="job_management",
        action="upload_bundle_complete",
        state={},
        thread_id="thread-job-upload-complete",
        docman=None,
    )

    assert r.get("ok") is True
    assert r.get("next") == "confirm_planning_schedule"
    uploaded_updates = _merge_values_for_node(capture_skill_ui_patches, "uploaded-files")
    assert uploaded_updates
    artifacts = uploaded_updates[-1].get("artifacts")
    assert isinstance(artifacts, list)
    labels = {str(item.get("label") or "") for item in artifacts if isinstance(item, dict)}
    assert {"到货表.xlsx", "人员信息表.xlsx"}.issubset(labels)


@pytest.mark.asyncio
async def test_job_management_confirm_planning_schedule_runs_plan_progress_planning_phase(
    skills_job_management_with_plan_progress: Path,
    capture_skill_ui_patches: list[dict],
    capture_task_status_updates: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    input_dir = skills_job_management_with_plan_progress / "plan_progress" / "input"
    (input_dir / "到货表.xlsx").write_text("arrival", encoding="utf-8")
    (input_dir / "人员信息表.xlsx").write_text("people", encoding="utf-8")

    mock_runner = AsyncMock(
        return_value={
            "ok": True,
            "bundle_path": "workspace/skills/plan_progress/ProjectData/RunTime/job_management_bundle.json",
            "summary": "Stage1 与 Stage2 已完成",
        }
    )
    monkeypatch.setattr(module_skill_runtime, "_run_plan_progress_planning_phase", mock_runner)

    r = await module_skill_runtime.run_module_action(
        module_id="job_management",
        action="confirm_planning_schedule",
        state={},
        thread_id="thread-job-planning",
        docman=None,
    )

    assert r.get("ok") is True
    assert r.get("next") == "confirm_engineering_schedule"
    mock_runner.assert_awaited_once()
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert summary_updates
    assert "Stage1 与 Stage2 已完成" in str(summary_updates[-1].get("content") or "")
    assert capture_task_status_updates
    latest = capture_task_status_updates[-1]
    modules = latest.get("modules")
    assert isinstance(modules, list)
    job = next((item for item in modules if item.get("name") == "作业管理"), None)
    assert job is not None
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert any(step.get("name") == "规划设计排期已确认" and step.get("done") is True for step in steps)


@pytest.mark.asyncio
async def test_job_management_confirm_engineering_schedule_runs_plan_progress_engineering_phase(
    skills_job_management_with_plan_progress: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    mock_runner = AsyncMock(return_value={"ok": True, "summary": "里程碑与排期已完成"})
    monkeypatch.setattr(module_skill_runtime, "_run_plan_progress_engineering_phase", mock_runner)

    r = await module_skill_runtime.run_module_action(
        module_id="job_management",
        action="confirm_engineering_schedule",
        state={"bundlePath": "workspace/skills/plan_progress/ProjectData/RunTime/job_management_bundle.json"},
        thread_id="thread-job-engineering",
        docman=None,
    )

    assert r.get("ok") is True
    assert r.get("next") == "confirm_cluster_schedule"
    mock_runner.assert_awaited_once()
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert summary_updates
    assert "里程碑与排期已完成" in str(summary_updates[-1].get("content") or "")


@pytest.mark.asyncio
async def test_job_management_confirm_cluster_schedule_runs_plan_progress_cluster_phase(
    skills_job_management_with_plan_progress: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    mock_runner = AsyncMock(return_value={"ok": True, "summary": "反思与收尾已完成"})
    monkeypatch.setattr(module_skill_runtime, "_run_plan_progress_cluster_phase", mock_runner)

    r = await module_skill_runtime.run_module_action(
        module_id="job_management",
        action="confirm_cluster_schedule",
        state={"bundlePath": "workspace/skills/plan_progress/ProjectData/RunTime/job_management_bundle.json"},
        thread_id="thread-job-cluster",
        docman=None,
    )

    assert r.get("ok") is True
    assert r.get("next") == "finish"
    mock_runner.assert_awaited_once()
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert summary_updates
    assert "反思与收尾已完成" in str(summary_updates[-1].get("content") or "")
