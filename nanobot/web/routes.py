"""aiohttp handlers for AGUI API."""

from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import os
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError
from loguru import logger

from nanobot.web.fs_ops import (
    BadRequestError,
    FsOpError,
    NotFoundError,
    open_in_os,
    resolve_in_workspace,
    trash_paths,
)
from nanobot.web.keys import AGENT_LOOP_KEY, APPROVAL_REGISTRY_KEY, CONFIG_KEY, RUN_REGISTRY_KEY
from nanobot.web.paths import normalize_file_query, resolve_file_target
from nanobot.web.run_registry import ApprovalRegistry, RunRegistry
from nanobot.web.skills import list_skills
from nanobot.web.sse import format_sse

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


async def _cleanup_chat_run(
    approvals: ApprovalRegistry,
    registry: RunRegistry,
    thread_id: str,
    run_id: str,
) -> None:
    """Best-effort, cancellation-safe release for per-thread run state."""
    await asyncio.shield(approvals.clear_run(thread_id, run_id))
    await asyncio.shield(registry.end(thread_id))


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
    # WebSocketResponse headers are already sent during the HTTP-101 handshake;
    # attempting to mutate them afterwards raises AssertionError in aiohttp 3.9+.
    # WebSocket connections also don't require CORS response headers.
    if isinstance(resp, web.WebSocketResponse):
        return resp
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


async def handle_trash_files(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)
    paths = data.get("paths")
    try:
        result = trash_paths(paths if isinstance(paths, list) else [])
        return web.json_response(result)
    except (BadRequestError, NotFoundError) as e:
        return _error(e.code, e.message, detail=e.detail, status=e.status)
    except FsOpError as e:
        return _error(e.code, e.message, detail=e.detail, status=e.status)
    except Exception as e:
        return _error("internal_error", "Failed to trash files", detail=str(e), status=500)


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
    human_in_the_loop = bool(data.get("humanInTheLoop", False))
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
    client_disconnected = False
    stream_prepared = False
    run_finished_sent = False
    process_task: asyncio.Task | None = None

    async def safe_write(event: str, payload: dict) -> None:
        nonlocal client_disconnected
        if client_disconnected:
            return
        async with write_lock:
            try:
                await response.write(format_sse(event, payload))
            except (ClientConnectionResetError, ConnectionResetError, RuntimeError):
                # Browser tab closed / stream cancelled while server is still producing
                # events. Treat as normal disconnect, not a run failure.
                client_disconnected = True
                if process_task is not None and not process_task.done():
                    process_task.cancel()

    try:
        await response.prepare(request)
        stream_prepared = True

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
            run_finished_sent = True
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
                nonlocal run_finished_sent
                # Ensure frontend always receives a terminal event even if stream
                # closes before process_direct returns.
                if resuming or run_finished_sent:
                    return
                await safe_write(
                    "RunFinished",
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "message": "".join(streamed_chunks),
                        "choices": run_choices,
                    },
                )
                run_finished_sent = True

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
                if not human_in_the_loop:
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
                process_task = asyncio.create_task(
                    agent.process_direct(
                        user_text,
                        session_key=thread_id,
                        channel="web",
                        chat_id=thread_id,
                        on_progress=on_progress,
                        on_stream=on_stream,
                        on_stream_end=on_stream_end,
                    )
                )
                out = await process_task
                final = (out.content if out is not None else "") or "".join(streamed_chunks)
                if not client_disconnected and not run_finished_sent:
                    await safe_write(
                        "RunFinished",
                        {
                            "threadId": thread_id,
                            "runId": run_id,
                            "message": final,
                            "choices": run_choices,
                        },
                    )
                    run_finished_sent = True
            except asyncio.CancelledError:
                if not client_disconnected:
                    await safe_write(
                        "RunFinished",
                        {
                            "threadId": thread_id,
                            "runId": run_id,
                            "error": {
                                "code": "cancelled",
                                "message": "Client disconnected; run cancelled.",
                            },
                        },
                    )
                    run_finished_sent = True
                raise
            except Exception as e:
                code = type(e).__name__
                msg = str(e) or code
                from loguru import logger

                if client_disconnected:
                    logger.info(
                        "AGUI /api/chat stream closed by client: thread_id={}, run_id={}",
                        thread_id,
                        run_id,
                    )
                else:
                    logger.exception("AGUI /api/chat run failed: {}", msg)
                    if os.environ.get("NANOBOT_AGUI_DEBUG"):
                        logger.debug("{}", traceback.format_exc())
                    # Detect HTML error responses (e.g., gateway/proxy returned HTML instead of JSON)
                    # This typically indicates API service issues like insufficient credits or gateway blocking
                    if "<!doctype html" in msg.lower() or "<html" in msg.lower():
                        msg = "⚠️ API 服务异常（余额不足或网关拦截），请检查账户状态。"
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
                    run_finished_sent = True
            finally:
                agent.reset_tool_approval_callback(token)
    except asyncio.CancelledError:
        client_disconnected = True
        if process_task is not None and not process_task.done():
            process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await process_task
        raise
    finally:
        if stream_prepared and not run_finished_sent and not client_disconnected:
            await safe_write(
                "RunFinished",
                {
                    "threadId": thread_id,
                    "runId": run_id,
                    "error": {
                        "code": "stream_closed",
                        "message": "Stream closed before terminal event.",
                    },
                },
            )
            run_finished_sent = True
        if stream_prepared and not client_disconnected:
            try:
                await response.write_eof()
            except (ClientConnectionResetError, ConnectionResetError, RuntimeError):
                pass
        if process_task is not None and not process_task.done():
            process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await process_task
        try:
            await _cleanup_chat_run(approvals, registry, thread_id, run_id)
        except Exception as e:
            logger.exception(
                "AGUI cleanup failed: thread_id={}, run_id={}, error={}",
                thread_id,
                run_id,
                str(e),
            )

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
        # Enhanced error message with more context for debugging
        return web.json_response({
            "detail": f"file not found: {normalized}",
            "resolved": str(target),
            "workspace": str(workspace),
        }, status=404)

    try:
        body = target.read_bytes()
    except PermissionError:
        return web.json_response({"detail": "permission denied"}, status=403)
    except OSError as e:
        return web.json_response({"detail": str(e)}, status=500)

    ctype = _content_type_for_file(target)
    return web.Response(body=body, content_type=ctype)


async def handle_browser(request: web.Request) -> web.WebSocketResponse:
    """WebSocket endpoint for remote browser streaming.

    Query params:
        url (str): Initial URL to navigate to (required).

    Protocol (server → client):
        {"type": "frame",  "data": "<base64_jpeg>", "url": "<current_page_url>"}
        {"type": "error",  "message": "<human readable>"}

    Protocol (client → server):
        {"action": "browser_interaction", "type": "click",  "x_percent": float, "y_percent": float}
        {"action": "browser_interaction", "type": "scroll", "deltaY": float}
    """
    from nanobot.web.browser_session import FRAME_INTERVAL, FRAME_INTERVAL_IDLE, IDLE_THRESHOLD, BrowserSession

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    initial_url = request.rel_url.query.get("url", "about:blank")
    # vw/vh: container CSS pixel dimensions sent by the frontend.
    # Backend renders at 2× DPR with exactly this aspect ratio → zero black bars.
    def _parse_int(key: str) -> int | None:
        raw = request.rel_url.query.get(key, "")
        try:
            v = int(raw)
            return v if v > 0 else None
        except ValueError:
            return None

    session = BrowserSession(
        container_width=_parse_int("vw"),
        container_height=_parse_int("vh"),
    )

    async def _send_json(payload: dict) -> None:
        try:
            if not ws.closed:
                await ws.send_json(payload)
        except Exception:
            pass

    # Start browser session – catch ALL exceptions, not just RuntimeError.
    # Playwright raises its own error types (e.g. playwright._impl._errors.Error)
    # when Chromium is not installed; those are not RuntimeError subclasses and
    # would silently escape a narrower except clause, causing the server to close
    # the WebSocket without sending an error frame to the client.
    try:
        await session.start(initial_url)
    except Exception as exc:
        await _send_json({"type": "error", "message": str(exc)})
        await ws.close()
        return ws

    # Wake-up event: interactions can request an immediate frame for snappier UX.
    interaction_wake = asyncio.Event()

    async def _frame_loop() -> None:
        static_frames = 0  # consecutive unchanged frames
        last_sent_url: str | None = None
        while not ws.closed:
            try:
                data = await session.screenshot_b64_if_changed()
                if data:
                    static_frames = 0
                    cur = session.current_url
                    payload: dict = {"type": "frame", "data": data}
                    # Only include url when it changes — smaller JSON + no useless React setState per frame
                    if cur != last_sent_url:
                        last_sent_url = cur
                        payload["url"] = cur
                    await _send_json(payload)
                else:
                    static_frames += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                err = str(exc)
                if any(kw in err for kw in ("Target closed", "has been closed", "Session closed")):
                    break  # page gone — exit cleanly
                logger.debug("Browser frame error: {}", exc)
            # Adaptive FPS: throttle to idle rate after IDLE_THRESHOLD static frames
            interval = FRAME_INTERVAL_IDLE if static_frames >= IDLE_THRESHOLD else FRAME_INTERVAL
            try:
                # Wait for either next interval or an interaction-triggered wakeup.
                await asyncio.wait_for(interaction_wake.wait(), timeout=interval)
                interaction_wake.clear()
            except asyncio.TimeoutError:
                pass

    frame_task = asyncio.ensure_future(_frame_loop())

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue

                action = payload.get("action")
                if action == "browser_interaction":
                    kind = payload.get("type")
                    try:
                        if kind == "click":
                            await session.click(
                                float(payload.get("x_percent", 0)),
                                float(payload.get("y_percent", 0)),
                            )
                            interaction_wake.set()
                        elif kind == "scroll":
                            dx = float(payload.get("delta_x", 0) or 0)
                            dy = float(payload.get("delta_y", 0) or payload.get("deltaY", 0) or 0)
                            await session.scroll(dx, dy)
                            interaction_wake.set()
                        elif kind in ("keypress", "keyboard"):
                            key = str(payload.get("key", ""))
                            if key:
                                await session.keyboard_input(
                                    key,
                                    ctrl=bool(payload.get("ctrl")),
                                    shift=bool(payload.get("shift")),
                                    alt=bool(payload.get("alt")),
                                )
                                interaction_wake.set()
                        elif kind == "insert_text":
                            # IME composition result (e.g. Chinese input)
                            text = str(payload.get("text", ""))
                            if text:
                                await session.insert_text(text)
                                interaction_wake.set()
                        elif kind == "refresh":
                            await session.reload()
                            interaction_wake.set()
                    except Exception as exc:
                        logger.debug("Browser interaction error: {}", exc)
            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                break
    finally:
        frame_task.cancel()
        try:
            await frame_task
        except asyncio.CancelledError:
            pass
        await session.close()

    return ws


def setup_routes(app: web.Application) -> None:
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/approve-tool", handle_approve)
    app.router.add_get("/api/file", handle_file)
    app.router.add_get("/api/skills", handle_skills)
    app.router.add_post("/api/open-folder", handle_open_folder)
    app.router.add_post("/api/trash-files", handle_trash_files)
    app.router.add_get("/api/browser", handle_browser)
    app.router.add_options("/api/chat", handle_options)
    app.router.add_options("/api/approve-tool", handle_options)
    app.router.add_options("/api/file", handle_options)
    app.router.add_options("/api/skills", handle_options)
    app.router.add_options("/api/open-folder", handle_options)
    app.router.add_options("/api/trash-files", handle_options)
