"""Tests for pure skill-first runtime driver (subprocess-based)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_skill_runtime_driver_runs_skill_driver_and_collects_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange a fake skill runtime/driver.py that emits one event line.
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo_skill"
    runtime_dir = skill_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")

    (runtime_dir / "driver.py").write_text(
        (
            "import json,sys\n"
            "req=json.loads(sys.stdin.read() or '{}')\n"
            "out={\n"
            "  'event':'chat.guidance',\n"
            "  'threadId': req.get('thread_id'),\n"
            "  'skillName': req.get('skill_name'),\n"
            "  'skillRunId': 'run-from-skill',\n"
            "  'payload': {'context': 'resumed', 'actions': []}\n"
            "}\n"
            "print(json.dumps(out,ensure_ascii=False))\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))

    from nanobot.web.skill_runtime_driver import run_skill_runtime_driver

    events = await run_skill_runtime_driver(
        skill_name="demo_skill",
        request={
            "thread_id": "t-1",
            "skill_name": "demo_skill",
            "request_id": "req-1",
            "action": "after_choice",
            "status": "ok",
            "result": {"selected": "a"},
        },
        python_executable=sys.executable,
    )

    assert len(events) == 1
    assert events[0]["event"] == "chat.guidance"
    assert events[0]["threadId"] == "t-1"
    assert events[0]["skillName"] == "demo_skill"

