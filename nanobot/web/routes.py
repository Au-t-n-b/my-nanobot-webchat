"""aiohttp handlers for AGUI API."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from aiohttp import web

from nanobot.web.keys import RUN_REGISTRY_KEY
from nanobot.web.run_registry import RunRegistry
from nanobot.web.sse import format_sse

if TYPE_CHECKING:
    pass


def _allowed_origins() -> list[str]:
    raw = os.environ.get("NANOBOT_AGUI_CORS_ORIGINS", "http://localhost:3000")
    out = [o.strip() for o in raw.split(",") if o.strip()]
    return out if out else ["http://localhost:3000"]


def _cors_headers(request: web.Request) -> dict[str, str]:
    origin = request.headers.get("Origin")
    allowed = _allowed_origins()
    if origin and origin in allowed:
        acao = origin
    elif allowed:
        acao = allowed[0]
    else:
        acao = "*"
    return {
        "Access-Control-Allow-Origin": acao,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
    }


@web.middleware
async def cors_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse | web.Response]],
) -> web.StreamResponse | web.Response:
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers(request))
    resp = await handler(request)
    for k, v in _cors_headers(request).items():
        resp.headers[k] = v
    return resp


async def handle_options(_request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers(_request))


async def handle_chat(request: web.Request) -> web.StreamResponse | web.Response:
    registry: RunRegistry = request.app[RUN_REGISTRY_KEY]
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return web.json_response({"detail": "Invalid JSON body"}, status=400)

    thread_id = data.get("threadId")
    run_id = data.get("runId")
    if thread_id is None or run_id is None or thread_id == "" or run_id == "":
        return web.json_response(
            {"detail": "threadId and runId are required"},
            status=400,
        )
    thread_id = str(thread_id)
    run_id = str(run_id)

    if not await registry.try_begin(thread_id, run_id):
        return web.json_response(
            {"detail": "Thread already has an active chat run"},
            status=409,
        )

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

    try:
        await response.prepare(request)
        hold = float(os.environ.get("NANOBOT_AGUI_SSE_HOLD_S", "0.15"))
        if hold > 0:
            await asyncio.sleep(hold)

        async def _write(event: str, payload: dict) -> None:
            await response.write(format_sse(event, payload))

        await _write(
            "RunStarted",
            {"threadId": thread_id, "runId": run_id, "model": "fake"},
        )
        await _write("TextMessageContent", {"delta": "hello "})
        await _write("TextMessageContent", {"delta": "world"})
        await _write(
            "RunFinished",
            {
                "threadId": thread_id,
                "runId": run_id,
                "message": "hello world",
            },
        )
    finally:
        await registry.end(thread_id)

    return response


async def handle_approve_stub(_request: web.Request) -> web.Response:
    return web.json_response({"detail": "not implemented"}, status=501)


async def handle_file_stub(_request: web.Request) -> web.Response:
    return web.json_response({"detail": "not implemented"}, status=501)


def setup_routes(app: web.Application) -> None:
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/approve-tool", handle_approve_stub)
    app.router.add_get("/api/file", handle_file_stub)
    app.router.add_options("/api/chat", handle_options)
    app.router.add_options("/api/approve-tool", handle_options)
    app.router.add_options("/api/file", handle_options)
