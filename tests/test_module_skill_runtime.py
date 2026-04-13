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


def _expected_boilerplate_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=workspace/skills/module_boilerplate/data/dashboard.json"


def _expected_zhgk_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/zhgk_module_case/data/dashboard.json"


def _expected_workbench_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/intelligent_analysis_workbench/data/dashboard.json"


def _expected_modeling_simulation_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/modeling_simulation_workbench/data/dashboard.json"


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
def skills_zhgk_module_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "zhgk_module_case"
    dst_root = tmp_path / "skills"
    shutil.copytree(src, dst_root / "zhgk_module_case")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root / "zhgk_module_case"


@pytest.mark.asyncio
async def test_load_module_config_zhgk_module_case(skills_zhgk_module_case: Path) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    cfg = load_module_config("zhgk_module_case")
    assert cfg.get("flow") == "zhgk_module_case"
    assert cfg.get("docId") == "dashboard:zhgk-module-case"


@pytest.mark.asyncio
async def test_zhgk_module_case_choose_strategy_emits_scene_choices(
    skills_zhgk_module_case: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    mock_choices = AsyncMock()
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_choices",
        mock_choices,
    )

    r = await run_module_action(
        module_id="zhgk_module_case",
        action="choose_strategy",
        state={},
        thread_id="thread-zhgk-case-choice",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "upload_evidence"
    mock_choices.assert_awaited_once()
    kwargs = mock_choices.await_args.kwargs
    assert kwargs.get("title") == "请选择本次智慧工勘的勘测场景："
    assert kwargs.get("options") == [
        {"id": "new_site", "label": "新址新建"},
        {"id": "site_expand", "label": "原址扩容"},
        {"id": "site_rebuild", "label": "原址新建"},
    ]
    for payload in capture_skill_ui_patches:
        assert payload.get("syntheticPath") == _expected_zhgk_synthetic_path()
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert {"stepper-main", "chart-donut", "chart-bar", "summary-text"}.issubset(merged)


@pytest.mark.asyncio
async def test_zhgk_module_case_finish_generates_handover_artifact(
    skills_zhgk_module_case: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="zhgk_module_case",
        action="finish",
        state={
            "standard": "site_expand",
            "upload": {"name": "深圳A03站点_BOQ与勘测包.zip"},
        },
        thread_id="thread-zhgk-case-finish",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("done") is True
    appends = _append_ops_from_patch_payloads(capture_skill_ui_patches)
    assert appends
    art_ops = [
        op
        for op in appends
        if str((op.get("target") or {}).get("nodeId") or "") == "artifacts"
        and str((op.get("target") or {}).get("field") or "") == "artifacts"
    ]
    assert art_ops
    value = art_ops[-1].get("value")
    assert isinstance(value, dict)
    assert value.get("id") == "zhgk-module-case-report-001"
    assert value.get("kind") == "md"
    assert value.get("label") == "智慧工勘模块迁移说明.md"
    report = skills_zhgk_module_case / "output" / "zhgk_module_case_handover.md"
    assert report.is_file()
    content = report.read_text(encoding="utf-8")
    assert "场景过滤" in content
    assert "勘测汇总" in content
    assert "报告生成" in content


@pytest.mark.asyncio
async def test_zhgk_module_case_after_upload_emits_partial_stream_updates(
    skills_zhgk_module_case: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="zhgk_module_case",
        action="after_upload",
        state={
            "standard": "site_expand",
            "upload": {"name": "深圳A03站点_BOQ与勘测包.zip"},
        },
        thread_id="thread-zhgk-case-after-upload",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "finish"
    assert len(capture_skill_ui_patches) >= 2, "after_upload 应分阶段推送而不是单次跳变"
    assert any((p.get("patch") or {}).get("isPartial") is True for p in capture_skill_ui_patches)
    assert any((p.get("patch") or {}).get("isPartial") is not True for p in capture_skill_ui_patches)

    stepper_updates = _merge_values_for_node(capture_skill_ui_patches, "stepper-main")
    assert stepper_updates, "应持续更新 stepper-main"
    latest_steps = stepper_updates[-1].get("steps")
    assert isinstance(latest_steps, list)
    assert latest_steps[-1]["status"] == "running"

    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert summary_updates, "应持续更新 summary-text"
    assert any("深圳A03站点_BOQ与勘测包.zip" in str(v.get("content") or "") for v in summary_updates)


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
