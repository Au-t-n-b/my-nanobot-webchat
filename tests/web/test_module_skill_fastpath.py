"""Fast-path：chat_card_intent 不进 LLM，且不调用 process_direct。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app
from nanobot.web.routes import _try_parse_chat_card_intent


def _first_sse_data(body: str, event_name: str) -> dict | None:
    blocks = body.split("\n\n")
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        ev = None
        data_line = None
        for ln in lines:
            if ln.startswith("event:"):
                ev = ln[len("event:") :].strip()
            elif ln.startswith("data:"):
                data_line = ln[len("data:") :].strip()
        if ev == event_name and data_line:
            return json.loads(data_line)
    return None


@pytest.fixture()
def local_tmp_dir() -> Path:
    root = Path(__file__).resolve().parents[2] / ".tmp" / "pytest-module-fastpath"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "case"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.asyncio
async def test_chat_module_action_fastpath_skips_process_direct(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = local_tmp_dir / "skills" / "module_skill_demo"
    root.mkdir(parents=True)
    (root / "module.json").write_text(
        json.dumps(
            {
                "moduleId": "module_skill_demo",
                "docId": "dashboard:test-fp",
                "dataFile": "workspace/skills/module_skill_demo/data/dashboard.json",
                "flow": "demo_compliance",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(local_tmp_dir / "skills"))

    agent = MagicMock()
    agent.model = "m1"
    agent.process_direct = AsyncMock()
    agent.close_mcp = AsyncMock()

    app = create_app(agent_loop=agent)
    intent = {
        "type": "chat_card_intent",
        "verb": "module_action",
        "cardId": "c1",
        "payload": {
            "moduleId": "module_skill_demo",
            "action": "cancel",
            "state": {},
        },
    }
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t-fastpath",
                "runId": "r-fastpath",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()
    fin = _first_sse_data(body, "RunFinished")
    assert fin is not None
    assert "error" not in fin
    # Fast-path 仅返回最小摘要；具体交互反馈由模块 flow 通过 ChatCard / Patch 呈现
    assert fin.get("message") in ("", None) or isinstance(fin.get("message"), str)
    agent.process_direct.assert_not_called()


def test_try_parse_chat_card_intent_start_job_management_defaults_to_jm_start() -> None:
    intent = _try_parse_chat_card_intent("启动 job_management")
    assert isinstance(intent, dict)
    assert intent.get("type") == "chat_card_intent"
    assert intent.get("verb") == "skill_runtime_start"
    payload = intent.get("payload")
    assert isinstance(payload, dict)
    assert payload.get("skillName") == "job_management"
    assert payload.get("action") == "jm_start"


def test_try_parse_chat_card_intent_strips_label_prefix_before_json() -> None:
    """Regression: '冷启动：' + project_guide JSON must not fall through to NL '启动 …' heuristics."""
    raw = (
        "冷启动："
        + json.dumps(
            {
                "type": "chat_card_intent",
                "verb": "skill_runtime_start",
                "payload": {
                    "type": "skill_runtime_start",
                    "skillName": "project_guide",
                    "requestId": "req-cold:t-1",
                    "action": "cold_start",
                    "threadId": "t-1",
                },
            },
            ensure_ascii=False,
        )
    )
    intent = _try_parse_chat_card_intent(raw)
    assert isinstance(intent, dict)
    assert intent.get("type") == "chat_card_intent"
    assert intent.get("verb") == "skill_runtime_start"
    payload = intent.get("payload")
    assert isinstance(payload, dict)
    assert payload.get("skillName") == "project_guide"
    assert payload.get("action") == "cold_start"
