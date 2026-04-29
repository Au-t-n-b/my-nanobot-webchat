"""Unit tests for ``nanobot.web.guide_tasks_resolver``.

These tests build a minimal ``project_guide/data/phases.json`` + per-phase
``data/guide_tasks.json`` + ``task_progress.json`` under a temporary
``NANOBOT_AGUI_SKILLS_ROOT``. They never touch ``templates/`` and never spawn
the actual driver subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_phases(skills_root: Path) -> None:
    _write_json(
        skills_root / "project_guide" / "data" / "phases.json",
        {
            "schemaVersion": 2,
            "phases": [
                {
                    "order": 0,
                    "displayName": "作业管理",
                    "moduleId": "job_management",
                    "skillDir": "job_management",
                    "startAction": "jm_start",
                    "startRequestId": "req-start-jobm",
                },
                {
                    "order": 1,
                    "displayName": "智慧工勘",
                    "moduleId": "smart_survey",
                    "skillDir": "zhgk",
                    "startAction": "start",
                    "startRequestId": "req-start-zhgk",
                },
            ],
        },
    )


def _seed_guide_tasks_jm(skills_root: Path) -> None:
    _write_json(
        skills_root / "job_management" / "data" / "guide_tasks.json",
        {
            "schemaVersion": 1,
            "moduleId": "job_management",
            "skillDir": "job_management",
            "intro": "请按子项推进",
            "tasks": [
                {
                    "id": "data_prep",
                    "displayName": "数据准备",
                    "trigger": "数据准备",
                    "aliases": ["开始数据准备"],
                    "skillRuntimeStart": {
                        "skillName": "job_management",
                        "action": "jm_start",
                        "requestId": "req-start-jm-data-prep",
                    },
                },
                {
                    "id": "plan_initial",
                    "displayName": "计划初排",
                    "trigger": "计划初排",
                    "placeholder": True,
                },
            ],
        },
    )


def _seed_task_progress(tmp_path: Path, *, jm_done: bool = False) -> Path:
    """Write ``task_progress.json`` and return its path; caller monkeypatches env."""
    progress_path = tmp_path / "task_progress.json"
    _write_json(
        progress_path,
        {
            "schemaVersion": 1,
            "progress": [
                {
                    "moduleId": "job_management",
                    "tasks": [{"name": "t1", "completed": jm_done}],
                },
                {
                    "moduleId": "smart_survey",
                    "tasks": [{"name": "t1", "completed": False}],
                },
            ],
        },
    )
    return progress_path


@pytest.fixture()
def isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))
    progress_path = _seed_task_progress(tmp_path, jm_done=False)
    monkeypatch.setenv("NANOBOT_TASK_PROGRESS_FILE", str(progress_path))
    return skills_root


def test_resolve_returns_none_when_phases_missing(isolated_workspace: Path) -> None:
    from nanobot.web.guide_tasks_resolver import resolve_current_phase_guide_tasks

    assert resolve_current_phase_guide_tasks() is None


def test_resolve_returns_none_when_guide_tasks_missing(isolated_workspace: Path) -> None:
    from nanobot.web.guide_tasks_resolver import resolve_current_phase_guide_tasks

    _seed_phases(isolated_workspace)
    assert resolve_current_phase_guide_tasks() is None


def test_resolve_current_phase_indexes_trigger_and_aliases(isolated_workspace: Path) -> None:
    from nanobot.web.guide_tasks_resolver import (
        resolve_current_phase_guide_tasks,
        match_phrase_to_intent,
    )

    _seed_phases(isolated_workspace)
    _seed_guide_tasks_jm(isolated_workspace)

    idx = resolve_current_phase_guide_tasks()
    assert idx is not None
    assert idx["skillDir"] == "job_management"
    phrase_index = idx["phrase_index"]
    assert "数据准备" in phrase_index
    assert "开始数据准备" in phrase_index
    assert "计划初排" not in phrase_index, "placeholder tasks must not appear"

    intent = match_phrase_to_intent("数据准备")
    assert intent is not None
    assert intent["type"] == "chat_card_intent"
    assert intent["verb"] == "skill_runtime_start"
    assert intent["payload"]["skillName"] == "job_management"
    assert intent["payload"]["action"] == "jm_start"
    assert intent["payload"]["requestId"] == "req-start-jm-data-prep"


def test_resolve_normalizes_whitespace_and_fullwidth(isolated_workspace: Path) -> None:
    from nanobot.web.guide_tasks_resolver import match_phrase_to_intent

    _seed_phases(isolated_workspace)
    _seed_guide_tasks_jm(isolated_workspace)

    assert match_phrase_to_intent("  数据准备  ") is not None
    assert match_phrase_to_intent("数据 准备") is not None  # internal whitespace collapsed


def test_resolve_skips_unrelated_phase_phrases(isolated_workspace: Path) -> None:
    """When current phase is job_management, zhgk's triggers should not match."""
    from nanobot.web.guide_tasks_resolver import match_phrase_to_intent

    _seed_phases(isolated_workspace)
    _seed_guide_tasks_jm(isolated_workspace)
    _write_json(
        isolated_workspace / "zhgk" / "data" / "guide_tasks.json",
        {
            "schemaVersion": 1,
            "moduleId": "smart_survey",
            "skillDir": "zhgk",
            "tasks": [
                {
                    "id": "scene_filter",
                    "displayName": "场景筛选",
                    "trigger": "场景筛选",
                    "skillRuntimeStart": {
                        "skillName": "zhgk",
                        "action": "start",
                        "requestId": "req-start-zhgk",
                    },
                }
            ],
        },
    )
    assert match_phrase_to_intent("场景筛选") is None


def test_resolve_advances_to_next_phase_when_jm_done(
    isolated_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once job_management tasks are all completed, the resolver should index zhgk's phrases."""
    from nanobot.web.guide_tasks_resolver import match_phrase_to_intent

    _seed_phases(isolated_workspace)
    _seed_guide_tasks_jm(isolated_workspace)
    _write_json(
        isolated_workspace / "zhgk" / "data" / "guide_tasks.json",
        {
            "schemaVersion": 1,
            "moduleId": "smart_survey",
            "skillDir": "zhgk",
            "tasks": [
                {
                    "id": "scene_filter",
                    "displayName": "场景筛选",
                    "trigger": "场景筛选",
                    "skillRuntimeStart": {
                        "skillName": "zhgk",
                        "action": "start",
                        "requestId": "req-start-zhgk",
                    },
                }
            ],
        },
    )
    progress_path = _seed_task_progress(tmp_path, jm_done=True)
    monkeypatch.setenv("NANOBOT_TASK_PROGRESS_FILE", str(progress_path))

    intent = match_phrase_to_intent("场景筛选")
    assert intent is not None
    assert intent["payload"]["skillName"] == "zhgk"
    assert match_phrase_to_intent("数据准备") is None


def test_resolve_returns_none_on_corrupt_guide_tasks(isolated_workspace: Path) -> None:
    from nanobot.web.guide_tasks_resolver import resolve_current_phase_guide_tasks

    _seed_phases(isolated_workspace)
    bad = isolated_workspace / "job_management" / "data" / "guide_tasks.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not valid json", encoding="utf-8")
    assert resolve_current_phase_guide_tasks() is None


def test_description_and_steps_do_not_pollute_phrase_index(isolated_workspace: Path) -> None:
    """``description`` / ``steps[]`` are display-only — they MUST NOT be matchable phrases."""
    from nanobot.web.guide_tasks_resolver import (
        resolve_current_phase_guide_tasks,
        match_phrase_to_intent,
    )

    _seed_phases(isolated_workspace)
    _write_json(
        isolated_workspace / "job_management" / "data" / "guide_tasks.json",
        {
            "schemaVersion": 1,
            "moduleId": "job_management",
            "skillDir": "job_management",
            "tasks": [
                {
                    "id": "data_prep",
                    "displayName": "数据准备",
                    "description": "围绕本期作业先把原始资料汇总并做基础校核",
                    "steps": ["上传作业资料", "选择策略", "确认基础信息"],
                    "trigger": "数据准备",
                    "skillRuntimeStart": {
                        "skillName": "job_management",
                        "action": "jm_start",
                        "requestId": "req-start-jm-data-prep",
                    },
                }
            ],
        },
    )
    idx = resolve_current_phase_guide_tasks()
    assert idx is not None
    phrase_index = idx["phrase_index"]
    # Only the trigger should be indexed; description / steps must be ignored.
    assert "数据准备" in phrase_index
    assert "围绕本期作业先把原始资料汇总并做基础校核" not in phrase_index
    assert "上传作业资料" not in phrase_index
    # Trigger's payload shape must remain pristine (no description / steps leakage into intent payload).
    intent = match_phrase_to_intent("数据准备")
    assert intent is not None
    assert set(intent.keys()) == {"type", "verb", "payload"}
    assert set(intent["payload"].keys()) == {"type", "skillName", "requestId", "action"}
