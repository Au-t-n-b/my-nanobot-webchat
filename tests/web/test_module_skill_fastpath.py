"""Fast-path：chat_card_intent 不进 LLM，且不调用 process_direct。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


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


@pytest.mark.asyncio
async def test_chat_module_action_fastpath_skips_process_direct(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "skills" / "module_skill_demo"
    root.mkdir(parents=True)
    (root / "module.json").write_text(
        json.dumps(
            {
                "docId": "dashboard:test-fp",
                "dataFile": "workspace/skills/module_skill_demo/data/dashboard.json",
                "flow": "demo_compliance",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(tmp_path / "skills"))

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
    payload = json.loads(fin["message"])
    assert payload.get("ok") is True
    agent.process_direct.assert_not_called()
