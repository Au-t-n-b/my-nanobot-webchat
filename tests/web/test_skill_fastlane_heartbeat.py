"""快路径心跳回归测试。

背景：``_handle_chat_skill_ui_fastlane`` 在 ``_dispatch_chat_intents_skill_first``
（如 job_management driver 的「计划初排」子进程）跑得超过 90s 时，前端
``hooks/useAgentChat.ts:STREAM_IDLE_TIMEOUT_MS = 90_000`` 会因 SSE 长时间不读到
任何字节而抛 ``SSE stream idle timeout``，把整轮 run 误判为失败。

修复点：在 fastlane 中加一个 10s 周期的 ``Heartbeat`` 事件协程（与主 ``handle_chat``
路径同款机制），与主 emit 共用 ``write_lock`` 防止 SSE 帧被切散。本测试通过
monkeypatch 把心跳周期设为 50ms，并让 dispatch 阻塞 ~300ms，断言 SSE body 中
至少包含两条 ``Heartbeat`` 事件，且 ``RunStarted`` / ``RunFinished`` 仍按原顺序
出现。
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


@pytest.mark.asyncio
async def test_fastlane_emits_periodic_heartbeats_during_long_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """长时间 dispatch（无业务事件）期间，SSE body 必须出现多条 ``Heartbeat``。"""

    monkeypatch.setattr(
        "nanobot.web.routes._FASTLANE_HEARTBEAT_INTERVAL_S",
        0.05,
        raising=True,
    )

    async def slow_dispatch(**_kwargs):
        # 比心跳周期长得多，但比测试整体超时短得多，确保期间至少 5+ 次心跳触发。
        await asyncio.sleep(0.3)
        return True, ""

    monkeypatch.setattr(
        "nanobot.web.routes._dispatch_chat_intents_skill_first",
        slow_dispatch,
        raising=True,
    )

    agent = MagicMock()
    agent.model = "fake-fastlane-model"
    agent.close_mcp = AsyncMock()
    # MagicMock 默认 hasattr 都为真；setter 返回的 token 由 reset_* 自动接收。

    intent_json = json.dumps(
        {
            "type": "chat_card_intent",
            "verb": "skill_runtime_start",
            "payload": {
                "type": "skill_runtime_start",
                "skillName": "job_management",
                "requestId": "req-fastlane-hb-test",
                "action": "jm_start",
                "threadId": "t-fastlane-hb",
            },
        },
        ensure_ascii=False,
    )

    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t-fastlane-hb",
                "runId": "r-fastlane-hb",
                "messages": [{"role": "user", "content": intent_json}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()

    # 顺序：RunStarted（首发）→ ≥1 个 Heartbeat（dispatch 期间）→ RunFinished。
    assert "event: RunStarted" in body
    heartbeat_count = body.count("event: Heartbeat")
    assert heartbeat_count >= 2, (
        f"快路径心跳未生效；body 中 Heartbeat 出现 {heartbeat_count} 次，应 ≥2。\n"
        f"body 前 800 字：{body[:800]!r}"
    )
    assert "event: RunFinished" in body

    rs_idx = body.find("event: RunStarted")
    hb_idx = body.find("event: Heartbeat")
    rf_idx = body.find("event: RunFinished")
    assert 0 <= rs_idx < hb_idx < rf_idx, (
        f"事件顺序异常：RunStarted={rs_idx} Heartbeat={hb_idx} RunFinished={rf_idx}\n{body!r}"
    )


@pytest.mark.asyncio
async def test_fastlane_heartbeat_stops_after_run_finished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dispatch 立即返回时，``RunFinished`` 之后不应再追加 ``Heartbeat``。"""

    monkeypatch.setattr(
        "nanobot.web.routes._FASTLANE_HEARTBEAT_INTERVAL_S",
        0.02,
        raising=True,
    )

    async def fast_dispatch(**_kwargs):
        return True, ""

    monkeypatch.setattr(
        "nanobot.web.routes._dispatch_chat_intents_skill_first",
        fast_dispatch,
        raising=True,
    )

    agent = MagicMock()
    agent.model = "fake-fastlane-model"
    agent.close_mcp = AsyncMock()

    intent_json = json.dumps(
        {
            "type": "chat_card_intent",
            "verb": "skill_runtime_start",
            "payload": {
                "type": "skill_runtime_start",
                "skillName": "job_management",
                "requestId": "req-fastlane-hb-fast",
                "action": "jm_start",
                "threadId": "t-fastlane-hb-fast",
            },
        },
        ensure_ascii=False,
    )

    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t-fastlane-hb-fast",
                "runId": "r-fastlane-hb-fast",
                "messages": [{"role": "user", "content": intent_json}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()

    rf_idx = body.find("event: RunFinished")
    assert rf_idx >= 0
    tail = body[rf_idx + len("event: RunFinished") :]
    assert "event: Heartbeat" not in tail, (
        "RunFinished 之后不应再有 Heartbeat（心跳协程必须随 finally 立即取消）。\n"
        f"tail={tail!r}"
    )
