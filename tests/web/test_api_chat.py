"""AGUI HTTP integration tests."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


def _sse_event_payload(body: str, event_name: str) -> dict | None:
    """Parse first ``data:`` JSON after ``event: <name>``."""
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


@pytest.fixture(autouse=True)
def _fast_sse_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANOBOT_AGUI_SSE_HOLD_S", "0")


@pytest.mark.asyncio
async def test_post_chat_fake_sse_sequence() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            headers={"Origin": "http://localhost:3000"},
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")
        body = await resp.text()
        assert "event: RunStarted" in body
        assert "event: TextMessageContent" in body
        assert "event: RunFinished" in body
        finished_payload = _sse_event_payload(body, "RunFinished")
        assert finished_payload is not None
        assert "error" not in finished_payload


@pytest.mark.asyncio
async def test_post_chat_requires_thread_and_run() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"threadId": "x"})
        assert resp.status == 400


@pytest.mark.asyncio
async def test_approve_stub_bad_body() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r1 = await client.post("/api/approve-tool", json={})
        assert r1.status == 400


@pytest.mark.asyncio
async def test_approve_not_found_returns_404() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post(
            "/api/approve-tool",
            json={
                "threadId": "t1",
                "runId": "r1",
                "toolCallId": "tool_x",
                "approved": True,
            },
        )
        assert r.status == 404


@pytest.mark.asyncio
async def test_concurrent_same_thread_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANOBOT_AGUI_SSE_HOLD_S", "0.2")
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        task = asyncio.create_task(
            client.post(
                "/api/chat",
                json={
                    "threadId": "same",
                    "runId": "r1",
                    "messages": [],
                    "humanInTheLoop": False,
                },
            )
        )
        await asyncio.sleep(0.05)
        resp2 = await client.post(
            "/api/chat",
            json={
                "threadId": "same",
                "runId": "r2",
                "messages": [],
                "humanInTheLoop": False,
            },
        )
        assert resp2.status == 409
        resp1 = await task
        assert resp1.status == 200
        await resp1.text()


@pytest.mark.asyncio
async def test_cors_preflight_chat() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_preflight_127_default() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.options(
            "/api/chat",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:3000"


@pytest.mark.asyncio
async def test_cors_second_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "NANOBOT_AGUI_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.options(
            "/api/chat",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:3000"


@pytest.mark.asyncio
async def test_post_chat_requires_user_message_when_agent() -> None:
    agent = MagicMock()
    agent.model = "m1"
    agent.process_direct = AsyncMock(return_value=None)
    agent.close_mcp = AsyncMock()
    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 400


@pytest.mark.asyncio
async def test_post_chat_with_agent_maps_sse() -> None:
    from nanobot.bus.events import OutboundMessage

    agent = MagicMock()
    agent.model = "m1"

    async def pd(
        content,
        session_key="x",
        channel="x",
        chat_id="x",
        on_progress=None,
        on_stream=None,
        on_stream_end=None,
        model_name=None,
    ):
        assert content == "hi"
        assert session_key == "t1"
        assert channel == "web"
        assert chat_id == "t1"
        assert model_name is None
        if on_progress:
            await on_progress("thinking", tool_hint=False)
        if on_stream:
            await on_stream("A")
        return OutboundMessage(channel="web", chat_id=session_key, content="A")

    agent.process_direct = AsyncMock(side_effect=pd)
    agent.close_mcp = AsyncMock()

    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [{"role": "user", "content": "hi"}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()
        assert "event: RunStarted" in body
        rs = _sse_event_payload(body, "RunStarted")
        assert rs is not None
        assert rs.get("model") == "m1"
        assert "event: StepStarted" in body
        assert "event: TextMessageContent" in body
        fin = _sse_event_payload(body, "RunFinished")
        assert fin is not None
        assert fin.get("message") == "A"
        assert "error" not in fin


@pytest.mark.asyncio
async def test_post_chat_rejects_non_string_model_name() -> None:
    agent = MagicMock()
    agent.model = "m1"
    agent.process_direct = AsyncMock(return_value=None)
    agent.close_mcp = AsyncMock()
    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [{"role": "user", "content": "hi"}],
                "humanInTheLoop": False,
                "model_name": 123,
            },
        )
        assert resp.status == 400
        body = await resp.json()
        assert body.get("detail") == "model_name must be a string"
    agent.process_direct.assert_not_called()


@pytest.mark.asyncio
async def test_post_chat_model_name_override_updates_runstarted_and_call_arg() -> None:
    from nanobot.bus.events import OutboundMessage

    agent = MagicMock()
    agent.model = "m1"

    async def pd(
        content,
        session_key="x",
        channel="x",
        chat_id="x",
        on_progress=None,
        on_stream=None,
        on_stream_end=None,
        model_name=None,
    ):
        assert content == "hi"
        assert session_key == "t1"
        assert channel == "web"
        assert chat_id == "t1"
        assert model_name == "glm-4.7"
        if on_stream:
            await on_stream("A")
        return OutboundMessage(channel="web", chat_id=session_key, content="A")

    agent.process_direct = AsyncMock(side_effect=pd)
    agent.close_mcp = AsyncMock()

    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [{"role": "user", "content": "hi"}],
                "humanInTheLoop": False,
                "model_name": "glm-4.7",
            },
        )
        assert resp.status == 200
        body = await resp.text()
        rs = _sse_event_payload(body, "RunStarted")
        assert rs is not None
        assert rs.get("model") == "glm-4.7"


@pytest.mark.asyncio
async def test_post_chat_agent_error_emits_error_events() -> None:
    agent = MagicMock()
    agent.model = "m1"
    agent.process_direct = AsyncMock(side_effect=RuntimeError("boom"))
    agent.close_mcp = AsyncMock()
    app = create_app(agent_loop=agent)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [{"role": "user", "content": "x"}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()
        assert "event: Error" in body
        err = _sse_event_payload(body, "Error")
        assert err is not None
        assert err.get("code") == "RuntimeError"
        fin = _sse_event_payload(body, "RunFinished")
        assert fin is not None
        assert "error" in fin
        assert fin["error"]["code"] == "RuntimeError"


@pytest.mark.asyncio
async def test_post_chat_includes_choices_on_run_finished() -> None:
    from nanobot.bus.events import OutboundMessage

    class ToolCall:
        def __init__(self) -> None:
            self.id = "tool_1"
            self.name = "present_choices"
            self.arguments = {
                "choices": [
                    {"label": "A", "value": "a"},
                    {"label": "B", "value": "b"},
                ]
            }

    class FakeAgent:
        def __init__(self) -> None:
            self.model = "m1"
            self._cb = None
            self.close_mcp = AsyncMock()

        def set_tool_approval_callback(self, cb):
            self._cb = cb
            return "tok"

        def reset_tool_approval_callback(self, _token):
            self._cb = None

        async def process_direct(self, *_args, **_kwargs):
            assert self._cb is not None
            await self._cb(ToolCall())
            return OutboundMessage(channel="web", chat_id="t1", content="done")

    app = create_app(agent_loop=FakeAgent())
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [{"role": "user", "content": "pick one"}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()
        fin = _sse_event_payload(body, "RunFinished")
        assert fin is not None
        assert fin.get("choices") == [
            {"label": "A", "value": "a"},
            {"label": "B", "value": "b"},
        ]


@pytest.mark.asyncio
async def test_post_chat_human_in_the_loop_false_skips_tool_pending() -> None:
    from nanobot.bus.events import OutboundMessage

    class ToolCall:
        def __init__(self) -> None:
            self.id = "tool_1"
            self.name = "write_file"
            self.arguments = {"path": "a.txt", "content": "x"}

    class FakeAgent:
        def __init__(self) -> None:
            self.model = "m1"
            self._cb = None
            self.close_mcp = AsyncMock()

        def set_tool_approval_callback(self, cb):
            self._cb = cb
            return "tok"

        def reset_tool_approval_callback(self, _token):
            self._cb = None

        async def process_direct(self, *_args, **_kwargs):
            assert self._cb is not None
            approved = await self._cb(ToolCall())
            assert approved is True
            return OutboundMessage(channel="web", chat_id="t1", content="done")

    app = create_app(agent_loop=FakeAgent())
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t1",
                "runId": "r2",
                "messages": [{"role": "user", "content": "write file"}],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
        body = await resp.text()
        assert "event: ToolPending" not in body
