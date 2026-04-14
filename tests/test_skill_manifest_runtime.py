"""Tests for declarative skill manifest parsing, loading, and runtime gates."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from nanobot.skills.manifest_loader import load_skill_manifest
from nanobot.skills.manifest_runtime import run_manifest_step
from nanobot.skills.manifest_schema import parse_skill_manifest


@pytest.fixture()
def local_tmp_dir() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp" / "pytest-skill-manifest-runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"case-{uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _file_gate_manifest(path: str) -> dict[str, object]:
    return {
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
                        "path": path,
                        "match": "strict",
                    }
                ],
                "upload": {
                    "saveDir": "skills/plan_progress/input",
                    "multiple": True,
                    "accept": ".xlsx",
                },
                "next": "choose_mode",
            }
        ],
    }


def _choice_gate_manifest() -> dict[str, object]:
    return {
        "version": 1,
        "entry": "choose_mode",
        "stateNamespace": "plan_progress",
        "steps": [
            {
                "id": "choose_mode",
                "type": "choice_gate",
                "title": "请选择执行模式",
                "description": "请选择后续处理模式",
                "options": [
                    {"id": "standard", "label": "标准模式"},
                    {"id": "fast", "label": "快速模式"},
                ],
                "storeAs": "selected_mode",
                "nextByChoice": {
                    "standard": "run_standard",
                    "fast": "run_fast",
                },
            }
        ],
    }


def _fixed_action_manifest() -> dict[str, object]:
    return {
        "version": 1,
        "entry": "execute_fixed_action",
        "stateNamespace": "plan_progress",
        "steps": [
            {
                "id": "execute_fixed_action",
                "type": "fixed_action",
                "title": "固定动作执行",
                "message": "两个文件已齐全，已自动进入固定动作。",
                "statePatch": {
                    "all_inputs_ready": True,
                    "execution_mode": "fixed",
                },
            }
        ],
    }


def test_parse_valid_file_gate_manifest() -> None:
    manifest = parse_skill_manifest(
        _file_gate_manifest("workspace/skills/plan_progress/input/到货表.xlsx")
    )
    assert manifest.entry == "prepare_inputs"
    assert manifest.state_namespace == "plan_progress"
    assert manifest.steps[0].type == "file_gate"


def test_parse_manifest_rejects_unknown_step_type() -> None:
    raw = {
        "version": 1,
        "entry": "x",
        "stateNamespace": "demo",
        "steps": [{"id": "x", "type": "unknown"}],
    }
    with pytest.raises(ValueError, match="unknown step type"):
        parse_skill_manifest(raw)


def test_parse_valid_fixed_action_manifest() -> None:
    manifest = parse_skill_manifest(_fixed_action_manifest())
    assert manifest.entry == "execute_fixed_action"
    assert manifest.steps[0].type == "fixed_action"


def test_load_skill_manifest_reads_workspace_file(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = local_tmp_dir / "skills"
    skill_dir = skills_root / "plan_progress"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry": "prepare_inputs",
                "stateNamespace": "plan_progress",
                "steps": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))
    manifest = load_skill_manifest("plan_progress")
    assert manifest.state_namespace == "plan_progress"


def test_load_skill_manifest_requires_file(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = local_tmp_dir / "skills"
    (skills_root / "plan_progress").mkdir(parents=True)
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))
    with pytest.raises(FileNotFoundError, match="skill.manifest.json"):
        load_skill_manifest("plan_progress")


def test_run_file_gate_returns_completed_when_all_files_exist(local_tmp_dir: Path) -> None:
    workspace_root = local_tmp_dir / "workspace"
    target = workspace_root / "skills" / "plan_progress" / "input" / "到货表.xlsx"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")
    manifest = parse_skill_manifest(
        _file_gate_manifest("workspace/skills/plan_progress/input/到货表.xlsx")
    )
    result = run_manifest_step(
        manifest=manifest,
        step_id="prepare_inputs",
        state={},
        workspace_root=workspace_root,
    )
    assert result["status"] == "completed"
    assert result["next"] == "choose_mode"
    assert result["stepId"] == "prepare_inputs"


def test_run_file_gate_returns_blocked_when_files_missing(local_tmp_dir: Path) -> None:
    workspace_root = local_tmp_dir / "workspace"
    workspace_root.mkdir(parents=True)
    manifest = parse_skill_manifest(
        _file_gate_manifest("workspace/skills/plan_progress/input/到货表.xlsx")
    )
    result = run_manifest_step(
        manifest=manifest,
        step_id="prepare_inputs",
        state={},
        workspace_root=workspace_root,
    )
    assert result["status"] == "blocked_by_hitl"
    assert result["stepType"] == "file_gate"
    assert result["upload"]["saveDir"] == "skills/plan_progress/input"
    missing = result["missingFiles"]
    assert isinstance(missing, list)
    assert missing[0]["label"] == "到货表.xlsx"


def test_run_choice_gate_blocks_when_selection_missing() -> None:
    manifest = parse_skill_manifest(_choice_gate_manifest())
    result = run_manifest_step(manifest=manifest, step_id="choose_mode", state={})
    assert result["status"] == "blocked_by_hitl"
    assert result["stepType"] == "choice_gate"
    assert result["storeAs"] == "selected_mode"
    assert len(result["options"]) == 2


def test_run_choice_gate_accepts_valid_selection() -> None:
    manifest = parse_skill_manifest(_choice_gate_manifest())
    result = run_manifest_step(
        manifest=manifest,
        step_id="choose_mode",
        state={},
        input_data={"optionId": "standard"},
    )
    assert result["status"] == "completed"
    assert result["next"] == "run_standard"
    assert result["state"]["selected_mode"] == "standard"


def test_run_choice_gate_rejects_invalid_selection() -> None:
    manifest = parse_skill_manifest(_choice_gate_manifest())
    with pytest.raises(ValueError, match="unknown option"):
        run_manifest_step(
            manifest=manifest,
            step_id="choose_mode",
            state={},
            input_data={"optionId": "missing"},
        )


def test_run_fixed_action_returns_completed_with_summary() -> None:
    manifest = parse_skill_manifest(_fixed_action_manifest())
    result = run_manifest_step(
        manifest=manifest,
        step_id="execute_fixed_action",
        state={"upload_count": 2},
    )
    assert result["status"] == "completed"
    assert result["summary"] == "两个文件已齐全，已自动进入固定动作。"
    assert result["state"]["upload_count"] == 2
    assert result["state"]["all_inputs_ready"] is True
    assert result["state"]["execution_mode"] == "fixed"
