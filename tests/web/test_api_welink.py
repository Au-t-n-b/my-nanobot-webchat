"""WeLink SSE bridge integration tests (MVP: text-only)."""

from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


def _parse_welink_sse(body: str) -> list[dict]:
    """Parse `data: <json>` blocks into list of dicts."""
    out: list[dict] = []
    for block in body.split("\n\n"):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        for ln in lines:
            if ln.startswith("data:"):
                payload = ln[len("data:") :].strip()
                out.append(json.loads(payload))
    return out


@pytest.mark.asyncio
async def test_welink_stream_fake_agent_sse_sequence() -> None:
    app = create_app(agent_loop=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/welink/chat/stream",
            json={
                "type": "text",
                "content": "你好",
                "sendUserAccount": "u1",
                "topicId": 100,
                "messageId": 200,
            },
        )
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")
        body = await resp.text()
        items = _parse_welink_sse(body)
        assert items, body
        assert items[-1].get("isFinish") is True
        assert items[-1].get("code") in ("0", 0)


@pytest.mark.asyncio
async def test_welink_requires_core_fields() -> None:
    app = create_app(agent_loop=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/welink/chat/stream", json={"type": "text"})
        assert resp.status == 400

