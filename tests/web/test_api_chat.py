"""AGUI HTTP integration tests."""

from __future__ import annotations

import asyncio
import json

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
            json={
                "threadId": "t1",
                "runId": "r1",
                "messages": [],
                "humanInTheLoop": False,
            },
        )
        assert resp.status == 200
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
async def test_approve_and_file_stubs() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r1 = await client.post("/api/approve-tool", json={})
        assert r1.status == 501
        assert (await r1.json()).get("detail") == "not implemented"
        r2 = await client.get("/api/file", params={"path": "/x"})
        assert r2.status == 501


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
