"""Fast-path test: routes._try_parse_chat_card_intent honours guide_tasks phrases.

Verifies that the JSON path still wins, the phrase path produces the same payload
shape as a row click, and unrelated text falls through to the legacy heuristic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture()
def workspace_with_guide_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

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
                }
            ],
        },
    )
    _write_json(
        skills_root / "job_management" / "data" / "guide_tasks.json",
        {
            "schemaVersion": 1,
            "moduleId": "job_management",
            "skillDir": "job_management",
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
    progress_path = tmp_path / "task_progress.json"
    _write_json(
        progress_path,
        {
            "schemaVersion": 1,
            "progress": [
                {
                    "moduleId": "job_management",
                    "tasks": [{"name": "t1", "completed": False}],
                }
            ],
        },
    )
    monkeypatch.setenv("NANOBOT_TASK_PROGRESS_FILE", str(progress_path))
    return skills_root


def test_phrase_match_returns_chat_card_intent(workspace_with_guide_tasks: Path) -> None:
    from nanobot.web.routes import _try_parse_chat_card_intent

    intent = _try_parse_chat_card_intent("数据准备")
    assert intent is not None
    assert intent["type"] == "chat_card_intent"
    assert intent["verb"] == "skill_runtime_start"
    payload = intent["payload"]
    assert payload["skillName"] == "job_management"
    assert payload["action"] == "jm_start"
    assert payload["requestId"] == "req-start-jm-data-prep"


def test_alias_match_returns_chat_card_intent(workspace_with_guide_tasks: Path) -> None:
    from nanobot.web.routes import _try_parse_chat_card_intent

    intent = _try_parse_chat_card_intent("开始数据准备")
    assert intent is not None
    assert intent["payload"]["action"] == "jm_start"


def test_placeholder_phrase_does_not_match(workspace_with_guide_tasks: Path) -> None:
    from nanobot.web.routes import _try_parse_chat_card_intent

    # "计划初排" is a placeholder; it must not produce a fast-path intent.
    intent = _try_parse_chat_card_intent("计划初排")
    assert intent is None


def test_unrelated_text_falls_through(workspace_with_guide_tasks: Path) -> None:
    from nanobot.web.routes import _try_parse_chat_card_intent

    # Pure prose with no JSON, no recognized phrase, no "启动 X" → returns None.
    assert _try_parse_chat_card_intent("帮我看看进度") is None


def test_legacy_start_module_still_works(workspace_with_guide_tasks: Path) -> None:
    from nanobot.web.routes import _try_parse_chat_card_intent

    intent = _try_parse_chat_card_intent("启动 job_management")
    assert intent is not None
    assert intent["payload"]["skillName"] == "job_management"
    assert intent["payload"]["action"] == "jm_start"


def test_json_intent_still_wins_over_phrase(workspace_with_guide_tasks: Path) -> None:
    """JSON path must short-circuit before phrase resolution."""
    from nanobot.web.routes import _try_parse_chat_card_intent

    raw = json.dumps(
        {
            "type": "chat_card_intent",
            "verb": "module_action",
            "cardId": "c1",
            "payload": {"moduleId": "job_management", "action": "noop", "state": {}},
        },
        ensure_ascii=False,
    )
    intent = _try_parse_chat_card_intent(raw)
    assert intent is not None
    assert intent["verb"] == "module_action"
