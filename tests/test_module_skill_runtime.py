"""模块 Skill 运行时与 Fast-path 解析测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def skills_module_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "skills"
    mod = root / "module_skill_demo"
    mod.mkdir(parents=True)
    (mod / "module.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "docId": "dashboard:test-demo",
                "dataFile": "workspace/skills/module_skill_demo/data/dashboard.json",
                "flow": "demo_compliance",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))
    return mod


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
