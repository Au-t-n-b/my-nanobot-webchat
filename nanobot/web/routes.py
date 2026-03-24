"""aiohttp handlers for AGUI API."""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiohttp import web

from nanobot.web.keys import AGENT_LOOP_KEY, RUN_REGISTRY_KEY
from nanobot.web.run_registry import RunRegistry
from nanobot.web.sse import format_sse

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


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


def _text_from_user_content(content: Any) -> str | None:
    if isinstance(content, str):
        t = content.strip()
        return t if t else None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                tx = block.get("text")
                if isinstance(tx, str) and tx.strip():
                    parts.append(tx.strip())
        if parts:
            return "\n".join(parts)
    return None


def _last_user_text(messages: Any) -> str | None:
    if not isinstance(messages, list):
        return None
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        got = _text_from_user_content(m.get("content"))
        if got:
            return got
    return None


async def handle_chat(request: web.Request) -> web.StreamResponse | web.Response:
    registry: RunRegistry = request.app[RUN_REGISTRY_KEY]
    agent: AgentLoop | None = request.app[AGENT_LOOP_KEY]

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

    messages = data.get("messages")
    user_text: str | None = None
    if agent is not None:
        user_text = _last_user_text(messages)
        if not user_text:
            return web.json_response(
                {"detail": "messages must include a non-empty user role string"},
                status=400,
            )

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

    write_lock = asyncio.Lock()

    async def safe_write(event: str, payload: dict) -> None:
        async with write_lock:
            await response.write(format_sse(event, payload))

    try:
        await response.prepare(request)

        if agent is None:
            hold = float(os.environ.get("NANOBOT_AGUI_SSE_HOLD_S", "0.15"))
            if hold > 0:
                await asyncio.sleep(hold)
            await safe_write(
                "RunStarted",
                {"threadId": thread_id, "runId": run_id, "model": "fake"},
            )
            await safe_write("TextMessageContent", {"delta": "hello "})
            await safe_write("TextMessageContent", {"delta": "world"})
            await safe_write(
                "RunFinished",
                {
                    "threadId": thread_id,
                    "runId": run_id,
                    "message": "hello world",
                },
            )
        else:
            model_name = agent.model or "unknown"
            await safe_write(
                "RunStarted",
                {"threadId": thread_id, "runId": run_id, "model": model_name},
            )

            streamed_chunks: list[str] = []

            async def on_progress(content: str, *, tool_hint: bool = False) -> None:
                if not (content or "").strip():
                    return
                step = "tool" if tool_hint else "thinking"
                await safe_write("StepStarted", {"stepName": step, "text": content})

            async def on_stream(delta: str) -> None:
                if delta:
                    streamed_chunks.append(delta)
                    await safe_write("TextMessageContent", {"delta": delta})

            async def on_stream_end(*, resuming: bool = False) -> None:
                del resuming  # reserved for future SSE boundaries

            try:
                assert user_text is not None
                out = await agent.process_direct(
                    user_text,
                    session_key=thread_id,
                    channel="web",
                    chat_id=thread_id,
                    on_progress=on_progress,
                    on_stream=on_stream,
                    on_stream_end=on_stream_end,
                )
                final = (out.content if out is not None else "") or "".join(streamed_chunks)
                await safe_write(
                    "RunFinished",
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "message": final,
                    },
                )
            except Exception as e:
                code = type(e).__name__
                msg = str(e) or code
                from loguru import logger

                logger.exception("AGUI /api/chat run failed: {}", msg)
                if os.environ.get("NANOBOT_AGUI_DEBUG"):
                    logger.debug("{}", traceback.format_exc())
                await safe_write(
                    "Error",
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "code": code,
                        "message": msg,
                    },
                )
                await safe_write(
                    "RunFinished",
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "error": {"code": code, "message": msg},
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
