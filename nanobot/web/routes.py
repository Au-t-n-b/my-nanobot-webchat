"""aiohttp handlers for AGUI API."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from nanobot.web.fs_ops import BadRequestError, FsOpError, NotFoundError, open_in_os, resolve_in_workspace
from nanobot.web.keys import AGENT_LOOP_KEY, APPROVAL_REGISTRY_KEY, CONFIG_KEY, RUN_REGISTRY_KEY
from nanobot.web.paths import normalize_file_query, resolve_file_target
from nanobot.web.run_registry import ApprovalRegistry, RunRegistry
from nanobot.web.skills import list_skills
from nanobot.web.sse import format_sse

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


def _allowed_origins() -> list[str]:
    raw = os.environ.get(
        "NANOBOT_AGUI_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    out = [o.strip() for o in raw.split(",") if o.strip()]
    return out if out else ["http://localhost:3000", "http://127.0.0.1:3000"]


def _cors_headers(request: web.Request) -> dict[str, str]:
    """Reflect ``Access-Control-Allow-Origin`` only when ``Origin`` is in the allow-list.

    Browsers require the response value to **exactly** match the request ``Origin``;
    sending the first allow-list entry when they differ causes a CORS failure.
    """
    origin = request.headers.get("Origin")
    allowed = _allowed_origins()
    headers: dict[str, str] = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
    }
    if origin and origin in allowed:
        headers["Access-Control-Allow-Origin"] = origin
    return headers


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


def _error(code: str, message: str, *, detail: str | None = None, status: int) -> web.Response:
    payload: dict[str, dict[str, str]] = {"error": {"code": code, "message": message}}
    if detail:
        payload["error"]["detail"] = detail
    return web.json_response(payload, status=status)


async def handle_skills(_request: web.Request) -> web.Response:
    try:
        return web.json_response({"items": list_skills()})
    except Exception as e:
        return _error("internal_error", "Failed to list skills", detail=str(e), status=500)


async def handle_open_folder(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)
    target = data.get("target")
    try:
        resolved = resolve_in_workspace(str(target))
        open_in_os(resolved)
        return web.json_response({"ok": True})
    except (BadRequestError, NotFoundError) as e:
        return _error(e.code, e.message, detail=e.detail, status=e.status)
    except FsOpError as e:
        return _error(e.code, e.message, detail=e.detail, status=e.status)
    except Exception as e:
        return _error("internal_error", "Failed to open folder", detail=str(e), status=500)


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
    approvals: ApprovalRegistry = request.app[APPROVAL_REGISTRY_KEY]
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

    # CORS must be on the first response bytes. Middleware runs after the handler
    # returns; for SSE the handler returns only when the stream ends, *after*
    # ``prepare()`` — so the browser never sees ACAO unless we attach it here.
    stream_headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    stream_headers.update(_cors_headers(request))
    response = web.StreamResponse(status=200, headers=stream_headers)

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
            run_choices: list[dict[str, str]] = []

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

            async def on_tool_approval(tc: Any) -> bool:
                tool_call_id = str(getattr(tc, "id", ""))
                tool_name = str(getattr(tc, "name", ""))
                arguments = getattr(tc, "arguments", {})
                arguments_str = (
                    arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
                )
                if tool_name == "present_choices":
                    args_obj = arguments if isinstance(arguments, dict) else {}
                    raw_choices = args_obj.get("choices", [])
                    if isinstance(raw_choices, list):
                        normalized: list[dict[str, str]] = []
                        for item in raw_choices:
                            if not isinstance(item, dict):
                                continue
                            label = str(item.get("label", "")).strip()
                            value = str(item.get("value", "")).strip()
                            if label and value:
                                normalized.append({"label": label, "value": value})
                        if normalized:
                            run_choices.clear()
                            run_choices.extend(normalized)
                    return True
                fut = await approvals.create(thread_id, run_id, tool_call_id)
                await safe_write(
                    "ToolPending",
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "arguments": arguments_str,
                    },
                )
                return await fut

            token = agent.set_tool_approval_callback(on_tool_approval)
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
                        "choices": run_choices,
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
                agent.reset_tool_approval_callback(token)
    finally:
        await approvals.clear_run(thread_id, run_id)
        await registry.end(thread_id)

    return response


async def handle_approve(request: web.Request) -> web.Response:
    approvals: ApprovalRegistry = request.app[APPROVAL_REGISTRY_KEY]
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return web.json_response({"detail": "Invalid JSON body"}, status=400)

    thread_id = str(data.get("threadId", ""))
    run_id = str(data.get("runId", ""))
    tool_call_id = str(data.get("toolCallId", ""))
    approved = data.get("approved")
    if not thread_id or not run_id or not tool_call_id or not isinstance(approved, bool):
        return web.json_response(
            {"detail": "threadId, runId, toolCallId, approved(bool) are required"},
            status=400,
        )

    ok = await approvals.resolve(thread_id, run_id, tool_call_id, approved)
    if not ok:
        return web.json_response({"detail": "No pending tool approval found"}, status=404)
    return web.json_response({"ok": True})


def _agui_workspace_root(config: Any | None) -> Path:
    if config is not None:
        return Path(config.workspace_path).resolve()
    env = os.environ.get("NANOBOT_AGUI_WORKSPACE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def _content_type_for_file(path: Path) -> str:
    guessed, _enc = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return "application/octet-stream"


async def handle_file(request: web.Request) -> web.Response:
    raw = request.rel_url.query.get("path")
    if raw is None or not str(raw).strip():
        return web.json_response({"detail": "path query parameter is required"}, status=400)

    normalized = normalize_file_query(str(raw))
    if not normalized:
        return web.json_response({"detail": "invalid path"}, status=400)

    cfg = request.app[CONFIG_KEY]
    workspace = _agui_workspace_root(cfg)

    try:
        target = resolve_file_target(normalized, workspace)
    except ValueError as e:
        return web.json_response({"detail": str(e)}, status=400)

    if not target.is_file():
        return web.json_response({"detail": "file not found"}, status=404)

    try:
        body = target.read_bytes()
    except PermissionError:
        return web.json_response({"detail": "permission denied"}, status=403)
    except OSError as e:
        return web.json_response({"detail": str(e)}, status=500)

    ctype = _content_type_for_file(target)
    return web.Response(body=body, content_type=ctype)


def setup_routes(app: web.Application) -> None:
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/approve-tool", handle_approve)
    app.router.add_get("/api/file", handle_file)
    app.router.add_get("/api/skills", handle_skills)
    app.router.add_post("/api/open-folder", handle_open_folder)
    app.router.add_options("/api/chat", handle_options)
    app.router.add_options("/api/approve-tool", handle_options)
    app.router.add_options("/api/file", handle_options)
    app.router.add_options("/api/skills", handle_options)
    app.router.add_options("/api/open-folder", handle_options)
