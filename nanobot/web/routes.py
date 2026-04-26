"""aiohttp handlers for AGUI API."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import mimetypes
import os
import re
import threading
import traceback
import uuid
import zipfile
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
from nanobot.web.keys import (
    AGENT_LOOP_KEY,
    APPROVAL_REGISTRY_KEY,
    CONFIG_KEY,
    PENDING_HITL_STORE_KEY,
    SKILL_RESUME_RUNNER_KEY,
    REMOTE_CENTER_CLIENT_FACTORY_KEY,
    REMOTE_CENTER_SESSION_STORE_KEY,
    RUN_REGISTRY_KEY,
)
from nanobot.web.paths import normalize_file_query, resolve_file_target
from nanobot.web.remote_center import RemoteCenterClient, RemoteCenterSessionStore
from nanobot.web.run_registry import ApprovalRegistry, RunRegistry
from nanobot.web.skills import (
    build_skill_archive,
    get_skill_dir,
    get_skills_root,
    list_modules,
    list_skills,
    parse_skill_metadata,
    read_remote_skill_metadata,
    skill_latest_modified_at,
    write_remote_skill_metadata,
)
from nanobot.web.task_progress import (
    default_task_progress_file_payload,
    load_task_status_payload,
    normalize_task_progress_payload,
)
from nanobot.web.sse import format_sse
from nanobot.web.local_auth_api import handle_auth_login, handle_auth_me, handle_auth_register
from nanobot.web.admin_members_api import handle_admin_members_list, handle_admin_member_patch

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


def _default_task_status_payload() -> dict[str, Any]:
    return normalize_task_progress_payload(default_task_progress_file_payload())


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


def _remote_center_store(request: web.Request) -> RemoteCenterSessionStore:
    return request.app[REMOTE_CENTER_SESSION_STORE_KEY]


def _remote_center_client_factory(request: web.Request) -> Any:
    return request.app.get("remote_center_client_factory") or request.app[REMOTE_CENTER_CLIENT_FACTORY_KEY]


def _require_remote_session(request: web.Request) -> RemoteCenterSessionStore | web.Response:
    store = _remote_center_store(request)
    if not store.is_connected():
        return _error("remote_not_connected", "Remote center session not established", status=400)
    return store


def _sanitize_skill_folder_name(value: str) -> str:
    safe = "".join("-" if ch in '\\/:*?"<>|' else ch for ch in str(value or "").strip())
    safe = " ".join(safe.split())
    return safe[:120] or "remote-skill"


def _list_archive_files(names: list[str]) -> list[str]:
    return [name for name in names if name and not name.endswith("/")]


def _common_prefix(paths: list[str]) -> str:
    if not paths:
        return ""
    segments_list = [path.split("/")[:-1] for path in paths]
    if not segments_list:
        return ""
    prefix: list[str] = []
    for group in zip(*segments_list, strict=False):
        if len(set(group)) != 1:
            break
        prefix.append(group[0])
    return "/".join(prefix)


def _archive_prefix(paths: list[str]) -> str:
    files = _list_archive_files(paths)
    anchors = [path for path in files if path.endswith("/SKILL.md") or path == "SKILL.md" or path.endswith("/_meta.json") or path == "_meta.json"]
    return _common_prefix(anchors or files)


def _write_imported_skill_archive(archive_bytes: bytes, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        names = zf.namelist()
        prefix = _archive_prefix(names)
        wrote_any = False
        for name in names:
            if name.endswith("/"):
                continue
            relative = name[len(prefix) + 1 :] if prefix and name.startswith(f"{prefix}/") else name
            if not relative:
                continue
            out_path = (target_dir / relative).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(zf.read(name))
            wrote_any = True
        if not wrote_any:
            raise ValueError("Archive did not contain writable files")


def _current_scope_and_project(store: RemoteCenterSessionStore) -> tuple[str, str | None]:
    project_id, _project_name = store.selected_project()
    return ("project", project_id) if project_id else ("personal", None)


async def handle_remote_center_session(request: web.Request) -> web.Response:
    return web.json_response(_remote_center_store(request).snapshot())


async def handle_remote_center_login(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)

    frontend_base = str(data.get("frontendBase") or "").strip()
    api_base = str(data.get("apiBase") or "").strip()
    work_id = str(data.get("workId") or "").strip()
    password = str(data.get("password") or "")
    if not frontend_base or not api_base or not work_id or not password:
        return _error("bad_request", "frontendBase, apiBase, workId and password are required", status=400)

    try:
        factory = _remote_center_client_factory(request)
        client = factory(frontend_base, api_base)
        payload = await client.login(work_id=work_id, password=password)
        snapshot = _remote_center_store(request).set_session(
            frontend_base=frontend_base,
            api_base=api_base,
            token=str(payload.get("token") or ""),
            user=payload.get("user") if isinstance(payload.get("user"), dict) else None,
            projects=payload.get("projects") if isinstance(payload.get("projects"), list) else [],
            client=client,
        )
        return web.json_response(snapshot)
    except Exception as e:
        return _error("remote_login_failed", "Failed to login to remote center", detail=str(e), status=502)


async def handle_remote_center_logout(request: web.Request) -> web.Response:
    return web.json_response(await _remote_center_store(request).clear())


async def handle_remote_center_project(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)

    store = _remote_center_store(request)
    if not store.is_connected():
        return _error("remote_not_connected", "Remote center session not established", status=400)

    project_id = str(data.get("projectId") or "").strip()
    if not project_id:
        return _error("bad_request", "projectId is required", status=400)
    try:
        return web.json_response(store.select_project(project_id))
    except KeyError:
        return _error("not_found", "Project not found in remote session", status=404)


async def handle_remote_org_skills(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    client = store.client()
    try:
        items = await client.list_org_skills()
        return web.json_response({"items": items})
    except Exception as e:
        return _error("remote_bad_response", "Failed to load remote organization skills", detail=str(e), status=502)


async def handle_remote_org_skill_detail(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    skill_id = request.match_info.get("skill_id", "")
    try:
        item = await store.client().get_org_skill(skill_id)
        return web.json_response(item)
    except KeyError:
        return _error("not_found", "Remote organization skill not found", status=404)
    except Exception as e:
        return _error("remote_bad_response", "Failed to load remote organization skill detail", detail=str(e), status=502)


async def handle_remote_org_skill_import(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)
    if str(data.get("target") or "") != "workspace-skills":
        return _error("bad_request", "Only workspace-skills import target is supported", status=400)
    skill_id = request.match_info.get("skill_id", "")
    user = store.user() or {}
    try:
        detail = await store.client().get_org_skill(skill_id)
        archive = await store.client().download_org_skill(skill_id, user_id=str(user.get("workId") or ""))
        target_dir = get_skills_root() / _sanitize_skill_folder_name(str(detail.get("name") or detail.get("title") or skill_id))
        _write_imported_skill_archive(archive, target_dir)
        write_remote_skill_metadata(
            target_dir,
            {
                "source": "remote-imported",
                "remoteSkillId": str(detail.get("id") or skill_id),
                "remoteTitle": str(detail.get("title") or detail.get("name") or skill_id),
                "organizationName": str(detail.get("organizationName") or ""),
                "businessType": str(detail.get("businessType") or ""),
                "deliveryType": str(detail.get("deliveryType") or ""),
                "sourceTemplateVersion": str(detail.get("version") or ""),
                "version": str(detail.get("version") or ""),
            },
        )
        return web.json_response({"ok": True, "target": "workspace-skills", "importedPath": str(target_dir.resolve())})
    except Exception as e:
        return _error("remote_bad_response", "Failed to import remote organization skill", detail=str(e), status=502)


async def handle_remote_org_skill_clone(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)
    scope = str(data.get("scope") or "").strip() or "project"
    project_id = str(data.get("projectId") or "").strip() or None
    skill_id = request.match_info.get("skill_id", "")
    user = store.user() or {}
    try:
        item = await store.client().clone_org_skill_to_personal(
            skill_id,
            scope=scope,
            project_id=project_id,
        )
        return web.json_response({"ok": True, "item": item})
    except Exception as e:
        return _error("remote_bad_response", "Failed to clone remote organization skill", detail=str(e), status=502)


async def handle_personal_skills_list(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    scope, project_id = _current_scope_and_project(store)
    try:
        items = await store.client().list_personal_skills(
            scope=scope,
            project_id=project_id,
        )
        return web.json_response({"items": items})
    except Exception as e:
        return _error("remote_bad_response", "Failed to load personal skills", detail=str(e), status=502)


async def handle_personal_skills_upload(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    reader = await request.post()
    scope = str(reader.get("scope") or "").strip() or "project"
    project_id = str(reader.get("projectId") or "").strip() or None
    upload = reader.get("file")
    if upload is None or not hasattr(upload, "file"):
        return _error("bad_request", "file is required", status=400)
    try:
        content = upload.file.read()
        item = await store.client().upload_personal_skill(
            filename=str(upload.filename or "skill.zip"),
            content=content,
            scope=scope,
            project_id=project_id,
        )
        return web.json_response({"ok": True, "item": item})
    except Exception as e:
        return _error("upload_failed", "Failed to upload personal skill", detail=str(e), status=502)


async def handle_personal_artifacts_list(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    scope, project_id = _current_scope_and_project(store)
    user = store.user() or {}
    try:
        items = await store.client().list_personal_artifacts(
            scope=scope,
            project_id=project_id,
            user_id=str(user.get("workId") or ""),
        )
        return web.json_response({"items": items})
    except Exception as e:
        return _error("remote_bad_response", "Failed to load personal artifacts", detail=str(e), status=502)


async def handle_personal_artifacts_upload(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    reader = await request.post()
    scope = str(reader.get("scope") or "").strip() or "project"
    project_id = str(reader.get("projectId") or "").strip() or None
    uploads = reader.getall("files")
    if not uploads:
        return _error("bad_request", "files are required", status=400)
    try:
        files = [
            {
                "filename": str(item.filename or "file.bin"),
                "clientFileKey": str(item.filename or "file.bin"),
                "content": item.file.read(),
                "contentType": str(item.content_type or "application/octet-stream"),
            }
            for item in uploads
        ]
        items = await store.client().upload_personal_artifacts(
            files=files,
            scope=scope,
            project_id=project_id,
        )
        return web.json_response({"ok": True, "items": items})
    except Exception as e:
        return _error("upload_failed", "Failed to upload personal artifacts", detail=str(e), status=502)


async def handle_personal_artifacts_upload_from_session(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)
    scope = str(data.get("scope") or "").strip() or "project"
    project_id = str(data.get("projectId") or "").strip() or None
    raw_paths = data.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return _error("bad_request", "paths must be a non-empty array", status=400)
    try:
        files = []
        for raw in raw_paths:
            try:
                resolved = resolve_in_workspace(str(raw))
            except BadRequestError:
                return _error("invalid_upload_source", "paths must stay within workspace", status=400)
            files.append(
                {
                    "filename": resolved.name,
                    "clientFileKey": resolved.name,
                    "content": resolved.read_bytes(),
                    "contentType": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
                }
            )
        items = await store.client().upload_personal_artifacts(
            files=files,
            scope=scope,
            project_id=project_id,
        )
        return web.json_response({"ok": True, "items": items})
    except NotFoundError as e:
        return _error(e.code, e.message, detail=e.detail, status=e.status)
    except Exception as e:
        return _error("upload_failed", "Failed to upload session artifacts", detail=str(e), status=502)


async def handle_skills(_request: web.Request) -> web.Response:
    try:
        return web.json_response({"items": list_skills()})
    except Exception as e:
        return _error("internal_error", "Failed to list skills", detail=str(e), status=500)


async def handle_modules(_request: web.Request) -> web.Response:
    try:
        return web.json_response({"items": list_modules()})
    except Exception as e:
        return _error("internal_error", "Failed to list modules", detail=str(e), status=500)


async def handle_skill_publish(request: web.Request) -> web.Response:
    store_or_response = _require_remote_session(request)
    if isinstance(store_or_response, web.Response):
        return store_or_response
    store = store_or_response
    try:
        data = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return _error("bad_request", "Invalid JSON body", status=400)

    skill_name = str(data.get("skillName") or "").strip()
    target = str(data.get("target") or "").strip()
    if not skill_name or target not in {"personal", "backflow"}:
        return _error("bad_request", "skillName and target(personal|backflow) are required", status=400)
    try:
        skill_dir = get_skill_dir(skill_name)
    except ValueError:
        return _error("bad_request", "invalid skillName", status=400)
    skill_file = skill_dir / "SKILL.md"
    if not skill_dir.is_dir() or not skill_file.is_file():
        return _error("not_found", "Skill not found", status=404)

    user = store.user() or {}
    user_id = str(user.get("workId") or "")
    scope, project_id = _current_scope_and_project(store)
    archive = build_skill_archive(skill_dir)
    if not archive:
        return _error("bad_request", "Skill archive is empty", status=400)
    metadata = parse_skill_metadata(skill_dir)

    try:
        if target == "personal":
            item = await store.client().upload_personal_skill(
                filename=f"{skill_name}.zip",
                content=archive,
                scope=scope,
                project_id=project_id,
                user_id=user_id,
            )
            return web.json_response({"ok": True, "target": "personal", "item": item})

        remote_meta = read_remote_skill_metadata(skill_dir) or {}
        raw_source_template_id = str(remote_meta.get("remoteSkillId") or "").strip()
        if not raw_source_template_id.isdigit():
            return _error("bad_request", "Only remote-imported skills can be collected back to remote assets", status=400)
        item = await store.client().collect_skill_to_remote(
            filename=f"{skill_name}.zip",
            content=archive,
            title=str(remote_meta.get("remoteTitle") or metadata.get("name") or skill_name),
            description=str(metadata.get("description") or ""),
            tags=[str(tag) for tag in metadata.get("tags") or [] if str(tag).strip()],
            business_type=str(remote_meta.get("businessType") or "迁移调优"),
            delivery_type=str(remote_meta.get("deliveryType") or ""),
            organization_name=str(remote_meta.get("organizationName") or ""),
            project_name=project_id,
            uploader_id=user_id,
            version=str(metadata.get("version") or remote_meta.get("version") or "1.0.0"),
            source_template_version=str(
                remote_meta.get("sourceTemplateVersion") or remote_meta.get("version") or metadata.get("version") or "1.0.0"
            ),
            local_last_modified_at=skill_latest_modified_at(skill_dir),
            base_skill_id=int(raw_source_template_id),
            base_skill_title=str(remote_meta.get("remoteTitle") or metadata.get("name") or skill_name),
        )
        return web.json_response({"ok": True, "target": "backflow", "item": item})
    except Exception as e:
        return _error("upload_failed", "Failed to publish skill", detail=str(e), status=502)


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


# E2E：用户发送此前缀时跳过 LLM，流式返回预设产物文本（与前端 fileIndex 路径规则对齐）
_COLD_START_SKILL_INTERCEPT_PREFIX = "/run-skill cold_start_analysis"


def _cold_start_skill_mock_stream_deltas() -> list[str]:
    """Split preset assistant text into SSE ``TextMessageContent`` chunks.

    Includes a GFM-style fenced block (``json path=…``) for the report payload, plus
    ``Output/…`` in backticks so ``frontend/lib/fileIndex.extractFilesFromContent`` can
    drive artifact chips / preview (see also ``AgentMarkdown`` link normalization).
    """
    report_obj: dict[str, Any] = {
        "taskId": "CS-2026-0424",
        "status": "completed",
        "metrics": {
            "signalStrength": "-75dBm",
            "interferenceLevel": "Low",
            "estimatedSetupTime": "45 mins",
        },
        "risks": [
            "坐标存在轻微偏移，已自动校准",
            "当前频段可能受周边微波塔影响",
        ],
    }
    json_body = json.dumps(report_obj, ensure_ascii=False, indent=2)
    full = (
        "🚀 收到指令！我已经为您完成了基站的冷启动环境勘测与分析。"
        "以下是生成的勘测报告与异常诊断参数，请点击查看详情：\n\n"
        "```json path=cold_start_analysis.json\n"
        f"{json_body}\n"
        "```\n\n"
        "侧栏产物 / 预览联动路径：`Output/cold_start_analysis.json`\n"
    )
    chunks: list[str] = []
    acc = ""
    for line in full.splitlines(keepends=True):
        acc += line
        if len(acc) >= 96:
            chunks.append(acc)
            acc = ""
    if acc:
        chunks.append(acc)
    return chunks if chunks else [full]


def _try_parse_chat_card_intent(text: str) -> dict[str, Any] | None:
    """若用户消息内含 ``chat_card_intent`` JSON 对象，则解析为 dict；否则 None。

    支持整段即为 JSON，或前面有分隔线/说明文字（如 ``————{\\\"type\\\":\\\"chat_card_intent\\\"...``），
    避免误走 LLM 导致模型谎称「没有工具」。
    """
    t = (text or "").strip()
    if not t:
        return None
    dec = json.JSONDecoder()
    # 从每个 ``{`` 起尝试 raw_decode，取第一个合法且 type 匹配的 object
    search_from = 0
    while True:
        i = t.find("{", search_from)
        if i < 0:
            break
        chunk = t[i:].lstrip()
        try:
            obj, _end = dec.raw_decode(chunk)
        except json.JSONDecodeError:
            search_from = i + 1
            continue
        if isinstance(obj, dict) and obj.get("type") == "chat_card_intent":
            return obj
        search_from = i + 1

    # Fallback fast-path: allow natural language "开启/打开/启动 <moduleId>" to start a module skill.
    # This avoids relying on the LLM to emit the JSON envelope.
    #
    # Accept common variants like:
    # - "启动 dashboard_only"
    # - "启动 dashboard_only 模块"
    # - "好的，启动 dashboard_only 模块"
    # - "打开 dashboard_only 大盘"
    m = re.search(r"(?:开启|打开|启动)\s*[`'\"]?([A-Za-z0-9_-]+)[`'\"]?(?:\s*(?:模块|大盘|skill))?\s*$", t)
    if m:
        module_id = m.group(1).strip()
        # platform_capability_lab expects action=pcs_start (see its dashboard button).
        if module_id == "platform_capability_lab":
            action = "pcs_start"
        elif module_id == "job_management":
            # Do not guess action names for delivered skills; use a neutral default.
            action = "start"
        else:
            action = "start"
        return {
            "type": "chat_card_intent",
            "verb": "skill_runtime_start",
            "payload": {
                "type": "skill_runtime_start",
                "skillName": module_id,
                "requestId": f"req-start-{module_id}",
                "action": action,
            },
        }

    return None


_SKILL_HITL_FASTLANE_VERBS = frozenset({"skill_runtime_result", "skill_runtime_resume"})


def _is_skill_hitl_fastlane_intent(intent: dict[str, Any] | None) -> bool:
    if not isinstance(intent, dict):
        return False
    if intent.get("type") != "chat_card_intent":
        return False
    return str(intent.get("verb") or "").strip() in _SKILL_HITL_FASTLANE_VERBS


def _is_skill_ui_fastlane_intent(intent: dict[str, Any] | None) -> bool:
    """True for HITL resume intents or direct ``skill_runtime_start`` (NL / SDUI button)."""
    if not isinstance(intent, dict) or intent.get("type") != "chat_card_intent":
        return False
    verb = str(intent.get("verb") or "").strip()
    if verb == "skill_runtime_start":
        return True
    return verb in _SKILL_HITL_FASTLANE_VERBS


async def _dispatch_chat_intents_skill_first(
    *,
    intent: dict[str, Any] | None,
    thread_id: str,
    docman: Any,
    request: web.Request,
    agent: Any,
) -> tuple[bool, str]:
    """默认 Skill-First：先 ``skill_runtime_bridge``，再 manifest。

    Workspace Skill（DevKit 交付）以 driver + SDUI 为主；legacy ``module_action`` 现默认禁用。
    """
    from nanobot.web.skill_manifest_bridge import dispatch_skill_manifest_intent
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    pending_store = request.app.get(PENDING_HITL_STORE_KEY)
    resume_runner = request.app.get(SKILL_RESUME_RUNNER_KEY)
    if pending_store is not None:
        try:
            await pending_store.init()
        except Exception:
            pass

    sessions = getattr(agent, "sessions", None) if agent is not None else None

    # Hard-disable legacy module_action unless explicitly enabled.
    # This keeps the platform as "generic + skill-first" only.
    verb = ""
    try:
        if isinstance(intent, dict):
            verb = str(intent.get("verb") or "").strip()
    except Exception:
        verb = ""
    if verb == "module_action" and not str(os.environ.get("NANOBOT_ENABLE_MODULE_ACTION") or "").strip():
        return True, json.dumps(
            {
                "ok": False,
                "error": "module_action 已禁用：请使用 skill_runtime_start（Skill-First）驱动模块流程",
            },
            ensure_ascii=False,
        )

    handled, hitl_message = await dispatch_skill_runtime_intent(
        intent,
        thread_id=thread_id,
        docman=docman,
        pending_hitl_store=pending_store,
        resume_runner=resume_runner,
        session_manager=sessions,
        session_key=thread_id,
        agent_loop=agent,
    )
    if not handled:
        handled, hitl_message = await dispatch_skill_manifest_intent(
            intent, thread_id=thread_id, docman=docman
        )
    return handled, hitl_message


async def _handle_chat_skill_ui_fastlane(
    *,
    request: web.Request,
    thread_id: str,
    run_id: str,
    intent: dict[str, Any],
    model_name_override: str | None,
) -> web.StreamResponse:
    """Process skill-first intents without ``RunRegistry.try_begin`` (no LLM slot).

    Covers ``skill_runtime_result`` / ``skill_runtime_resume`` (HITL) and
    ``skill_runtime_start`` (e.g. natural-language 开启 zhgk or SDUI start button).
    Intent 分发与主 ``handle_chat`` 一致：默认先 ``skill_runtime_bridge``，再 legacy ``module_action``。

    A long-lived LLM ``/api/chat`` stream holds the registry slot; without this lane,
    ``skill_runtime_result`` would get HTTP 409 and the skill would never resume.
    """
    from nanobot.agent.loop import AgentLoop

    agent: AgentLoop | None = request.app[AGENT_LOOP_KEY]
    model_name = model_name_override or (agent.model if agent else None) or "unknown"

    stream_headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    stream_headers.update(_cors_headers(request))
    response = web.StreamResponse(status=200, headers=stream_headers)
    await response.prepare(request)

    async def _write(event: str, payload: dict[str, Any]) -> None:
        await response.write(format_sse(event, payload))

    # ``skill_runtime_result`` / ``skill_runtime_resume`` run ``resume_runner`` which calls
    # ``emit_skill_runtime_event`` → ``emit_skill_ui_*_event`` ContextVars. The fastlane
    # handler does not go through ``handle_chat``'s per-request emitter setup, so without
    # rebinding here all dashboard.patch / chat cards / artifacts from the driver are no-ops
    # and the UI appears "stuck" until the user clicks Start again.
    emitter_stack: list[tuple[str, Any]] = []

    def _release_fastlane_skill_ui_emitters() -> None:
        if agent is None:
            emitter_stack.clear()
            return
        while emitter_stack:
            kind, tok = emitter_stack.pop()
            if kind == "thread":
                agent.reset_current_thread_id(tok)
            elif kind == "patch":
                agent.reset_skill_ui_patch_emitter(tok)
            elif kind == "chat":
                agent.reset_skill_ui_chat_card_emitter(tok)
            elif kind == "boot" and hasattr(agent, "reset_skill_ui_bootstrap_emitter"):
                agent.reset_skill_ui_bootstrap_emitter(tok)
            elif kind == "focus":
                agent.reset_module_session_focus_emitter(tok)
            elif kind == "task" and hasattr(agent, "reset_task_status_emitter"):
                agent.reset_task_status_emitter(tok)
            elif kind == "skill_result" and hasattr(agent, "reset_skill_agent_task_result_emitter"):
                agent.reset_skill_agent_task_result_emitter(tok)

    try:
        await _write("RunStarted", {"threadId": thread_id, "runId": run_id, "model": model_name})

        if agent is not None:
            async def emit_skill_ui_patch(payload: dict[str, Any]) -> None:
                await _write("SkillUiDataPatch", payload)

            async def emit_skill_ui_chat_card(payload: dict[str, Any]) -> None:
                await _write("SkillUiChatCard", payload)

            async def emit_skill_ui_bootstrap(payload: dict[str, Any]) -> None:
                await _write("SkillUiBootstrap", payload)

            async def emit_module_session_focus(payload: dict[str, Any]) -> None:
                await _write("ModuleSessionFocus", payload)

            async def emit_task_status(payload: dict[str, Any]) -> None:
                await _write("TaskStatusUpdate", payload)

            async def emit_skill_agent_task_result(payload: dict[str, Any]) -> None:
                await _write("SkillAgentTaskResult", payload)

            emitter_stack.append(("thread", agent.set_current_thread_id(thread_id)))
            emitter_stack.append(("patch", agent.set_skill_ui_patch_emitter(emit_skill_ui_patch)))
            emitter_stack.append(("chat", agent.set_skill_ui_chat_card_emitter(emit_skill_ui_chat_card)))
            if hasattr(agent, "set_skill_ui_bootstrap_emitter"):
                emitter_stack.append(("boot", agent.set_skill_ui_bootstrap_emitter(emit_skill_ui_bootstrap)))
            emitter_stack.append(("focus", agent.set_module_session_focus_emitter(emit_module_session_focus)))
            if hasattr(agent, "set_task_status_emitter"):
                emitter_stack.append(("task", agent.set_task_status_emitter(emit_task_status)))
            if hasattr(agent, "set_skill_agent_task_result_emitter"):
                emitter_stack.append(
                    ("skill_result", agent.set_skill_agent_task_result_emitter(emit_skill_agent_task_result))
                )

        handled, hitl_message = await _dispatch_chat_intents_skill_first(
            intent=intent,
            thread_id=thread_id,
            docman=None,
            request=request,
            agent=agent,
        )

        msg = str(hitl_message or "").strip()
        if not handled and not msg:
            msg = "intent not handled"
        await _write(
            "RunFinished",
            {
                "threadId": thread_id,
                "runId": run_id,
                "message": msg,
                "choices": [],
            },
        )
    except Exception as e:
        code = type(e).__name__
        msg = str(e) or code
        logger.exception("AGUI skill HITL fastlane failed: {}", msg)
        await _write(
            "Error",
            {
                "threadId": thread_id,
                "runId": run_id,
                "code": code,
                "message": msg,
            },
        )
        await _write(
            "RunFinished",
            {
                "threadId": thread_id,
                "runId": run_id,
                "error": {"code": code, "message": msg},
                "choices": [],
            },
        )
    finally:
        _release_fastlane_skill_ui_emitters()
    try:
        await response.write_eof()
    except (ClientConnectionResetError, ConnectionResetError, RuntimeError):
        pass
    return response


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
    raw_model_name = data.get("model_name")
    model_name_override: str | None = None
    if raw_model_name is not None:
        if not isinstance(raw_model_name, str):
            return web.json_response({"detail": "model_name must be a string"}, status=400)
        model_name_override = raw_model_name.strip() or None
    user_text: str | None = None
    if agent is not None:
        user_text = _last_user_text(messages)
        if not user_text:
            return web.json_response(
                {"detail": "messages must include a non-empty user role string"},
                status=400,
            )

    intent_preview: dict[str, Any] | None = None
    if agent is not None and user_text:
        intent_preview = _try_parse_chat_card_intent(user_text)
        if _is_skill_ui_fastlane_intent(intent_preview):
            assert intent_preview is not None
            return await _handle_chat_skill_ui_fastlane(
                request=request,
                thread_id=thread_id,
                run_id=run_id,
                intent=intent_preview,
                model_name_override=model_name_override,
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

    def _client_is_closing() -> bool:
        """Best-effort detect client disconnect earlier than write() errors."""
        try:
            transport = request.transport
            # In aiohttp test servers, ``request.transport`` can be None even when the
            # client is still actively reading the SSE body. Treat None as
            # "unknown" (not closing) and rely on write() exceptions instead.
            return bool(transport is not None and transport.is_closing())
        except Exception:
            return False

    def _mark_disconnected_and_cancel() -> None:
        nonlocal client_disconnected
        if client_disconnected:
            return
        client_disconnected = True
        if process_task is not None and not process_task.done():
            process_task.cancel()

    async def safe_write(event: str, payload: dict) -> None:
        nonlocal client_disconnected
        # If the client already closed the connection, stop producing immediately.
        if client_disconnected or _client_is_closing():
            _mark_disconnected_and_cancel()
            return
        async with write_lock:
            try:
                await response.write(format_sse(event, payload))
            except (ClientConnectionResetError, ConnectionResetError, RuntimeError):
                # Browser tab closed / stream cancelled while server is still producing
                # events. Treat as normal disconnect, not a run failure.
                _mark_disconnected_and_cancel()

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
            model_name = model_name_override or agent.model or "unknown"
            await safe_write(
                "RunStarted",
                {"threadId": thread_id, "runId": run_id, "model": model_name},
            )

            async def emit_skill_ui_patch(payload: dict[str, Any]) -> None:
                await safe_write("SkillUiDataPatch", payload)

            async def emit_skill_ui_bootstrap(payload: dict[str, Any]) -> None:
                await safe_write("SkillUiBootstrap", payload)

            async def emit_skill_ui_chat_card(payload: dict[str, Any]) -> None:
                await safe_write("SkillUiChatCard", payload)

            async def emit_module_session_focus(payload: dict[str, Any]) -> None:
                await safe_write("ModuleSessionFocus", payload)

            async def emit_task_status(payload: dict[str, Any]) -> None:
                await safe_write("TaskStatusUpdate", payload)

            async def emit_skill_agent_task_result(payload: dict[str, Any]) -> None:
                await safe_write("SkillAgentTaskResult", payload)

            streamed_chunks: list[str] = []
            run_choices: list[dict[str, str]] = []

            cold_start_skill_mock = bool(
                (user_text or "").strip().startswith(_COLD_START_SKILL_INTERCEPT_PREFIX)
            )
            if cold_start_skill_mock:
                mock_streamed: list[str] = []
                for delta in _cold_start_skill_mock_stream_deltas():
                    mock_streamed.append(delta)
                    await safe_write("TextMessageContent", {"delta": delta})
                await safe_write(
                    "RunFinished",
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "message": "".join(mock_streamed),
                        "choices": run_choices,
                    },
                )
                run_finished_sent = True

            async def on_progress(content: str, *, tool_hint: bool = False) -> None:
                if client_disconnected or _client_is_closing():
                    _mark_disconnected_and_cancel()
                    return
                if not (content or "").strip():
                    return
                step = "tool" if tool_hint else "thinking"
                await safe_write("StepStarted", {"stepName": step, "text": content})

            async def on_stream(delta: str) -> None:
                if client_disconnected or _client_is_closing():
                    _mark_disconnected_and_cancel()
                    return
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
                if tool_name == "request_user_upload":
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

            if not cold_start_skill_mock:
                token = agent.set_tool_approval_callback(on_tool_approval)
                token_skill_ui_patch = agent.set_skill_ui_patch_emitter(emit_skill_ui_patch)
                token_skill_ui_chat = agent.set_skill_ui_chat_card_emitter(emit_skill_ui_chat_card)
                token_module_focus = agent.set_module_session_focus_emitter(emit_module_session_focus)
                token_thread_id = agent.set_current_thread_id(thread_id)
                pending_store = request.app.get(PENDING_HITL_STORE_KEY)
                token_pending_hitl = (
                    agent.set_pending_hitl_store(pending_store)
                    if pending_store is not None and hasattr(agent, "set_pending_hitl_store")
                    else None
                )
                token_chat_docman = (
                    agent.set_chat_docman(None) if hasattr(agent, "set_chat_docman") else None
                )
                token_skill_ui_bootstrap = (
                    agent.set_skill_ui_bootstrap_emitter(emit_skill_ui_bootstrap)
                    if hasattr(agent, "set_skill_ui_bootstrap_emitter")
                    else None
                )
                token_task_status = (
                    agent.set_task_status_emitter(emit_task_status)
                    if hasattr(agent, "set_task_status_emitter")
                    else None
                )
                token_skill_agent_task_result = (
                    agent.set_skill_agent_task_result_emitter(emit_skill_agent_task_result)
                    if hasattr(agent, "set_skill_agent_task_result_emitter")
                    else None
                )

                async def _sse_heartbeat() -> None:
                    """Independent keepalive: fires every 10 s regardless of agent output.

                    Prevents browser / proxy idle-timeout (the frontend enforces 20 s).
                    Uses a dedicated 'Heartbeat' event so the frontend can show a
                    lightweight 'thinking' indicator without polluting the step log.
                    """
                    try:
                        while not run_finished_sent and not client_disconnected:
                            await asyncio.sleep(10)
                            if run_finished_sent or client_disconnected:
                                break
                            await safe_write("Heartbeat", {"message": "Agent 正在处理中…"})
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass

                heartbeat_task = asyncio.create_task(_sse_heartbeat())
                try:
                    assert user_text is not None

                    intent = _try_parse_chat_card_intent(user_text)
                    handled, hitl_message = await _dispatch_chat_intents_skill_first(
                        intent=intent,
                        thread_id=thread_id,
                        docman=None,
                        request=request,
                        agent=agent,
                    )
                    if handled:
                        if not client_disconnected and not run_finished_sent:
                            await safe_write(
                                "RunFinished",
                                {
                                    "threadId": thread_id,
                                    "runId": run_id,
                                    "message": hitl_message,
                                    "choices": run_choices,
                                },
                            )
                            run_finished_sent = True
                    else:
                        process_task = asyncio.create_task(
                            agent.process_direct(
                                user_text,
                                session_key=thread_id,
                                channel="web",
                                chat_id=thread_id,
                                on_progress=on_progress,
                                on_stream=on_stream,
                                on_stream_end=on_stream_end,
                                model_name=model_name_override,
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
                    # Cancel the keepalive heartbeat regardless of how the run ended
                    heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat_task
                    agent.reset_tool_approval_callback(token)
                    agent.reset_skill_ui_patch_emitter(token_skill_ui_patch)
                    agent.reset_skill_ui_chat_card_emitter(token_skill_ui_chat)
                    agent.reset_module_session_focus_emitter(token_module_focus)
                    agent.reset_current_thread_id(token_thread_id)
                    if token_pending_hitl is not None and hasattr(agent, "reset_pending_hitl_store"):
                        agent.reset_pending_hitl_store(token_pending_hitl)
                    if token_chat_docman is not None and hasattr(agent, "reset_chat_docman"):
                        agent.reset_chat_docman(token_chat_docman)
                    if token_skill_ui_bootstrap is not None and hasattr(
                        agent, "reset_skill_ui_bootstrap_emitter"
                    ):
                        agent.reset_skill_ui_bootstrap_emitter(token_skill_ui_bootstrap)
                    if token_task_status is not None and hasattr(agent, "reset_task_status_emitter"):
                        agent.reset_task_status_emitter(token_task_status)
                    if token_skill_agent_task_result is not None and hasattr(
                        agent, "reset_skill_agent_task_result_emitter"
                    ):
                        agent.reset_skill_agent_task_result_emitter(token_skill_agent_task_result)
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
                    "choices": run_choices,
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


def _default_skills_root_path() -> Path:
    return (Path.home() / ".nanobot" / "workspace" / "skills").resolve()


def _agui_workspace_root(config: Any | None) -> Path:
    """Root directory for ``/api/upload`` and ``GET /api/file``.

    ``FilePicker`` sends ``targetDir`` like ``skills/<module>/ProjectData/Input``. That must resolve
    under the same directory tree as ``get_skills_root()`` (skill subprocess cwd). If Nanobot config
    points ``agents.defaults.workspace`` somewhere else while skills still default to
    ``~/.nanobot/workspace/skills``, uploads used to land only under the config path and the folder
    you open under ``.nanobot/workspace/skills/...`` stayed empty.
    """
    for key in ("NANOBOT_AGUI_WORKSPACE", "NANOBOT_AGUI_WORKSPACE_ROOT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()

    skills_root = get_skills_root().resolve()
    skills_parent = skills_root.parent.resolve()
    default_skills = _default_skills_root_path()
    skills_env_set = bool(os.environ.get("NANOBOT_AGUI_SKILLS_ROOT", "").strip())

    if config is not None:
        cfg_ws = Path(config.workspace_path).resolve()
        cfg_skills = (cfg_ws / "skills").resolve()
        try:
            if cfg_skills == skills_root:
                return cfg_ws
        except Exception:
            pass
        if (
            not skills_env_set
            and skills_root == default_skills
            and cfg_ws.resolve() != skills_parent.resolve()
        ):
            logger.warning(
                "AGUI: agents.defaults.workspace ({}) does not contain get_skills_root() ({}); "
                "using {} for /api/upload and /api/file so uploads match the default skills tree.",
                cfg_ws,
                skills_root,
                skills_parent,
            )
            return skills_parent
        return cfg_ws

    return Path.cwd().resolve()


def _content_type_for_file(path: Path) -> str:
    guessed, _enc = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return "application/octet-stream"


def _safe_upload_basename(name: str) -> str:
    raw = Path(str(name or "")).name
    out = "".join(c for c in raw if c.isalnum() or c in "._-")
    out = out[:180].strip(".")
    return out or "upload.bin"


async def handle_workspace_upload(request: web.Request) -> web.Response:
    """POST /api/upload — 保存到 AGUI workspace（供会话内 FilePicker）。

    multipart 字段：
    - ``file``：必填
    - ``purpose``：可选，用于默认落盘子目录 ``uploads/<purpose>/``
    - ``targetDir`` / ``saveRelativeDir``：可选，workspace 相对目录，文件名为客户端原始文件名（净化后）
    """
    cfg = request.app[CONFIG_KEY]
    workspace = _agui_workspace_root(cfg)
    try:
        data = await request.post()
    except Exception as e:
        return web.json_response({"detail": f"invalid multipart form: {e}"}, status=400)

    upload = data.get("file")
    if upload is None or not hasattr(upload, "file"):
        return web.json_response({"detail": "file is required"}, status=400)

    purpose = str(data.get("purpose") or "").strip() or "upload"
    save_dir_raw = str(data.get("targetDir") or data.get("saveRelativeDir") or "").strip()

    content = upload.file.read()
    max_bytes = 52 * 1024 * 1024
    if len(content) > max_bytes:
        return web.json_response({"detail": "file too large (max 52MB)"}, status=400)

    filename = _safe_upload_basename(str(upload.filename or "file.bin"))
    try:
        if save_dir_raw:
            norm_dir = normalize_file_query(save_dir_raw).strip("/")
            # Strict anti-traversal: deny absolute & drive paths early with explicit errors.
            if norm_dir.startswith("/") or norm_dir.startswith("\\") or re.match(r"^[A-Za-z]:", norm_dir):
                return web.json_response({"detail": "invalid targetDir (must be workspace-relative)"}, status=400)
            if not norm_dir or ".." in norm_dir.split("/"):
                return web.json_response({"detail": "invalid targetDir"}, status=400)
            if ":" in norm_dir:
                return web.json_response({"detail": "invalid targetDir (illegal character ':')"}, status=400)
            rel = f"{norm_dir}/{filename}"
        else:
            rel = f"uploads/{purpose}/{uuid.uuid4().hex}_{filename}"
        dest = resolve_file_target(rel, workspace)
    except ValueError as e:
        return web.json_response({"detail": str(e)}, status=400)

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    except OSError as e:
        logger.error("workspace upload write failed | path={} | {}", dest, e)
        return web.json_response({"detail": "failed to write file"}, status=500)

    logical = str(dest.resolve().relative_to(workspace.resolve())).replace("\\", "/")
    file_id = f"ws:{logical}"
    logical_path = f"workspace/{logical}"
    return web.json_response({"fileId": file_id, "logicalPath": logical_path})


_skill_ui_state_lock = threading.Lock()
_skill_ui_state_revision = 0


async def handle_skill_state_sync(request: web.Request) -> web.Response:
    """POST /api/skill/state/sync — SDUI upload / local widget state sync.

    ``SkillUiRuntimeProvider`` calls this after FilePicker uploads with ``behavior: immediate``.
    A full persisted store is not required for skill-first resume (files are on disk); this
    endpoint exists so the client gets HTTP 200 and an optional monotonic ``revision`` for acks.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "detail": "Invalid JSON body"}, status=400)

    doc_id = str(data.get("docId") or "").strip()
    key = str(data.get("key") or "").strip()
    if not doc_id or not key:
        return web.json_response({"ok": False, "detail": "docId and key are required"}, status=400)

    global _skill_ui_state_revision
    with _skill_ui_state_lock:
        _skill_ui_state_revision += 1
        rev = _skill_ui_state_revision
    return web.json_response({"ok": True, "revision": rev})


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

    # Platform-side UI policy: allow hiding SDUI Stepper without mutating user's local skill files.
    # Some dashboards are loaded via GET /api/file (not via SkillUiBootstrap), so bridge-level trimming
    # is not enough.
    try:
        # SkillUiWrapper 常用 path=skills/.../dashboard.json（可无 workspace/ 前缀），须匹配到
        if normalized.replace("\\", "/").endswith("skills/job_management/data/dashboard.json"):
            from nanobot.web.sdui_stepper_trim import strip_sdui_stepper_nodes

            try:
                doc = json.loads(body.decode("utf-8"))
                if isinstance(doc, dict):
                    body = json.dumps(strip_sdui_stepper_nodes(doc), ensure_ascii=False, indent=2).encode("utf-8")
            except Exception:
                # If parsing fails, fall back to raw bytes.
                pass
    except Exception:
        pass

    ctype = _content_type_for_file(target)
    return web.Response(body=body, content_type=ctype)


async def handle_task_status(request: web.Request) -> web.Response:
    try:
        return web.json_response(load_task_status_payload())
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"detail": "invalid task_progress.json"}, status=500)
    except OSError as e:
        return web.json_response({"detail": str(e)}, status=500)


async def handle_config_get(request: web.Request) -> web.Response:
    """GET /api/config — return ~/.nanobot/config.json as JSON."""
    cors = _cors_headers(request)
    from nanobot.config.loader import get_config_path  # local import to avoid circular deps

    SENSITIVE_PATTERNS = ("password", "apikey", "api_key", "token", "secret", "passwd")

    def _is_sensitive(key: str) -> bool:
        k = (key or "").lower()
        return any(p in k for p in SENSITIVE_PATTERNS)

    def _mask(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if _is_sensitive(str(k)) and isinstance(v, str) and v:
                    out[k] = "******"
                else:
                    out[k] = _mask(v)
            return out
        if isinstance(value, list):
            return [_mask(v) for v in value]
        return value

    config_path = get_config_path()
    if not config_path.exists():
        # Bootstrap-friendly: allow frontend "配置中心" to load defaults even when the
        # user has not created ~/.nanobot/config.json yet.
        #
        # NOTE: This is intentionally read-only; POST /api/config is the only way
        # to persist configuration.
        try:
            from nanobot.config.schema import Config
            from nanobot.web.keys import CONFIG_KEY

            cfg = request.app.get(CONFIG_KEY) or Config()
            payload = cfg.model_dump(mode="json", by_alias=True)
        except Exception:
            payload = {}
        return web.json_response(_mask(payload), headers=cors)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return web.json_response({"detail": "invalid config.json"}, status=500, headers=cors)
    except OSError as exc:
        return web.json_response({"detail": str(exc)}, status=500, headers=cors)
    return web.json_response(_mask(payload), headers=cors)


async def handle_runtime_get(request: web.Request) -> web.Response:
    """GET /api/runtime — return AGUI runtime mode for frontend hints."""
    cors = _cors_headers(request)
    from nanobot.web.keys import AGENT_LOOP_KEY, CONFIG_KEY

    agent = request.app.get(AGENT_LOOP_KEY)
    cfg = request.app.get(CONFIG_KEY)
    if agent is None and cfg is None:
        mode = "fake"
        needs_restart = False
    elif agent is None and cfg is not None:
        mode = "unconfigured"
        needs_restart = True
    else:
        mode = "configured"
        needs_restart = False

    return web.json_response(
        {
            "mode": mode,
            "agentLoop": agent is not None,
            "needsRestart": needs_restart,
        },
        headers=cors,
    )

async def handle_config_post(request: web.Request) -> web.Response:
    """POST /api/config — overwrite ~/.nanobot/config.json with request body."""
    cors = _cors_headers(request)
    from nanobot.config.loader import get_config_path
    from nanobot.web.run_registry import RunRegistry
    from nanobot.web.keys import AGENT_LOOP_KEY, CONFIG_KEY, RUN_REGISTRY_KEY

    SENSITIVE_PATTERNS = ("password", "apikey", "api_key", "token", "secret", "passwd")

    def _is_sensitive(key: str) -> bool:
        k = (key or "").lower()
        return any(p in k for p in SENSITIVE_PATTERNS)

    def _merge_with_original(incoming: Any, original: Any) -> Any:
        # If user posts "******" for a sensitive field, keep the existing value.
        if isinstance(incoming, dict) and isinstance(original, dict):
            out: dict[str, Any] = dict(original)
            for k, v in incoming.items():
                if _is_sensitive(str(k)) and v == "******":
                    continue
                out[k] = _merge_with_original(v, original.get(k))
            return out
        return incoming

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"detail": "request body must be valid JSON"}, status=400, headers=cors)

    # Prevent hot-reload while any chat run is active (avoids swapping providers mid-stream).
    registry: RunRegistry = request.app[RUN_REGISTRY_KEY]
    if await registry.active_count() > 0:
        return web.json_response(
            {"detail": "busy: chat run in progress"},
            status=409,
            headers=cors,
        )

    # Merge with existing config so masked sensitive fields ("******") keep their original values.
    config_path = get_config_path()
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    merged_body = _merge_with_original(body, existing)

    # Validate config against schema and build provider BEFORE writing to disk.
    try:
        from nanobot.config.schema import Config

        cfg = Config.model_validate(merged_body)
    except Exception as exc:
        return web.json_response({"detail": f"invalid config: {exc}"}, status=400, headers=cors)

    try:
        from nanobot.providers.factory import make_provider

        provider = make_provider(cfg)
    except Exception as exc:
        return web.json_response({"detail": f"invalid provider config: {exc}"}, status=400, headers=cors)

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = cfg.model_dump(mode="json", by_alias=True)
        config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        return web.json_response({"detail": str(exc)}, status=500, headers=cors)

    # Update in-memory config and hot-reload the running AgentLoop (if present).
    request.app[CONFIG_KEY] = cfg
    agent = request.app[AGENT_LOOP_KEY]
    if agent is None:
        # Bootstrap: if AGUI started in "unconfigured" mode (no AgentLoop),
        # create one now so the user does NOT need to restart `npm run dev`.
        try:
            from nanobot.agent.loop import AgentLoop
            from nanobot.bus.queue import MessageBus
            from nanobot.config.paths import get_cron_dir
            from nanobot.cron.service import CronService
            from nanobot.providers.factory import make_provider
            from nanobot.utils.helpers import sync_workspace_templates

            sync_workspace_templates(cfg.workspace_path, silent=True)
            bus = MessageBus()
            provider = make_provider(cfg)
            cron_store_path = get_cron_dir() / "jobs.json"
            cron = CronService(cron_store_path)
            agent = AgentLoop(
                bus=bus,
                provider=provider,
                workspace=cfg.workspace_path,
                model=cfg.agents.defaults.model,
                max_iterations=cfg.agents.defaults.max_tool_iterations,
                context_window_tokens=cfg.agents.defaults.context_window_tokens,
                web_search_config=cfg.tools.web.search,
                web_proxy=cfg.tools.web.proxy or None,
                exec_config=cfg.tools.exec,
                cron_service=cron,
                restrict_to_workspace=cfg.tools.restrict_to_workspace,
                mcp_servers=cfg.tools.mcp_servers,
                channels_config=cfg.channels,
            )
            request.app[AGENT_LOOP_KEY] = agent
            logger.info("config.json updated via API (AgentLoop bootstrapped)")
            return web.json_response(
                {
                    "ok": True,
                    "reloaded": True,
                    "current_model": cfg.agents.defaults.model,
                    "current_provider": cfg.agents.defaults.provider,
                    "bootstrapped": True,
                },
                headers=cors,
            )
        except Exception as exc:
            logger.warning("AgentLoop bootstrap failed after config update: {}", exc)
            return web.json_response({"detail": f"bootstrap failed: {exc}"}, status=500, headers=cors)
    else:
        try:
            await agent.reload_provider_and_model(
                provider=provider,
                model=cfg.agents.defaults.model,
            )
        except Exception as exc:
            logger.warning("Hot reload failed after config update: {}", exc)
            return web.json_response({"detail": f"hot reload failed: {exc}"}, status=500, headers=cors)

    logger.info("config.json updated via API (hot reload applied)")
    return web.json_response(
        {
            "ok": True,
            "reloaded": agent is not None,
            "current_model": cfg.agents.defaults.model,
            "current_provider": cfg.agents.defaults.provider,
        },
        headers=cors,
    )


async def handle_config_test(request: web.Request) -> web.Response:
    """POST /api/config/test — test provider connectivity without persisting config.

    Body:
      {
        "providerName": "zhipu",
        "apiKey": "xxxx" | "******",
        "apiBase": "https://..." | "" | null,
        "model": "glm-5" | null
      }
    """
    cors = _cors_headers(request)
    from nanobot.config.loader import get_config_path

    SENSITIVE_PATTERNS = ("password", "apikey", "api_key", "token", "secret", "passwd")

    def _is_sensitive(key: str) -> bool:
        k = (key or "").lower()
        return any(p in k for p in SENSITIVE_PATTERNS)

    def _merge_with_original(incoming: Any, original: Any) -> Any:
        # If user posts "******" for a sensitive field, keep the existing value.
        if isinstance(incoming, dict) and isinstance(original, dict):
            out: dict[str, Any] = dict(original)
            for k, v in incoming.items():
                if _is_sensitive(str(k)) and v == "******":
                    continue
                out[k] = _merge_with_original(v, original.get(k))
            return out
        return incoming

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"detail": "request body must be valid JSON"}, status=400, headers=cors)

    provider_name = str((body or {}).get("providerName") or "").strip()
    api_key = (body or {}).get("apiKey")
    api_base = (body or {}).get("apiBase")
    model = str((body or {}).get("model") or "").strip() or None
    if not provider_name:
        return web.json_response({"detail": "providerName is required"}, status=400, headers=cors)

    # Merge with on-disk config so masked sensitive fields keep their original values.
    config_path = get_config_path()
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    # Build a minimal patch that forces provider selection.
    patch: dict[str, Any] = {
        "agents": {
            "defaults": {
                "provider": provider_name,
            }
        },
        "providers": {
            provider_name: {
                "apiKey": api_key,
                "apiBase": api_base,
            }
        },
    }
    if model:
        patch["agents"]["defaults"]["model"] = model

    merged_body = _merge_with_original(patch, existing)

    # Validate and build provider
    try:
        from nanobot.config.schema import Config

        cfg = Config.model_validate(merged_body)
    except Exception as exc:
        return web.json_response({"detail": f"invalid config: {exc}"}, status=400, headers=cors)

    try:
        from nanobot.providers.factory import make_provider

        provider = make_provider(cfg)
    except Exception as exc:
        return web.json_response({"detail": f"invalid provider config: {exc}"}, status=400, headers=cors)

    # Probe by doing a tiny completion — fastest and works across providers.
    import asyncio
    import time

    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            provider.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
                model=cfg.agents.defaults.model,
            ),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        return web.json_response({"ok": False, "detail": "timeout after 12s"}, status=408, headers=cors)
    except Exception as exc:
        return web.json_response({"ok": False, "detail": str(exc)}, status=500, headers=cors)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if getattr(resp, "finish_reason", "") == "error":
        return web.json_response(
            {
                "ok": False,
                "detail": (resp.content or "Error calling LLM").strip()[:1000],
                "provider": provider_name,
                "model": cfg.agents.defaults.model,
                "latencyMs": elapsed_ms,
            },
            status=400,
            headers=cors,
        )

    return web.json_response(
        {
            "ok": True,
            "provider": provider_name,
            "model": cfg.agents.defaults.model,
            "latencyMs": elapsed_ms,
        },
        headers=cors,
    )


async def handle_providers_list(request: web.Request) -> web.Response:
    """GET /api/providers — list provider registry metadata for UI dropdowns."""
    cors = _cors_headers(request)
    from nanobot.providers.registry import PROVIDERS

    items: list[dict[str, Any]] = []
    for spec in PROVIDERS:
        items.append(
            {
                "name": spec.name,
                "label": spec.label,
                "keywords": list(spec.keywords),
                "isGateway": bool(spec.is_gateway),
                "isLocal": bool(spec.is_local),
                "isOAuth": bool(spec.is_oauth),
                "isDirect": bool(spec.is_direct),
                "defaultApiBase": spec.default_api_base or "",
                "litellmPrefix": spec.litellm_prefix or "",
                "stripModelPrefix": bool(spec.strip_model_prefix),
            }
        )
    return web.json_response({"providers": items}, headers=cors)


async def handle_welink_chat_stream(request: web.Request) -> web.StreamResponse | web.Response:
    """POST /welink/chat/stream — WeLink SSE chat bridge (MVP: text only).

    - Auth (optional): if env WELINK_AUTH_TOKEN is set, require Authorization match.
    - Input: WeLink JSON body (type/content/sendUserAccount/topicId/messageId/...).
    - Output: SSE lines of the form `data: <json>\\n\\n` with `code` and `isFinish`.
    - Heartbeat: emits an empty text chunk every 20s to avoid idle timeouts.
    """
    # Optional fixed-token auth (for quick internal integration)
    required = (os.environ.get("WELINK_AUTH_TOKEN") or "").strip()
    if required:
        got = (request.headers.get("Authorization") or "").strip()
        if got != required:
            return web.json_response({"code": "401", "message": "unauthorized"}, status=401)

    agent: AgentLoop | None = request.app[AGENT_LOOP_KEY]
    registry: RunRegistry = request.app[RUN_REGISTRY_KEY]

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"code": "400", "message": "request body must be valid JSON"}, status=400)

    msg_type = str(data.get("type") or "").strip()
    raw_content = data.get("content")
    send_user = str(data.get("sendUserAccount") or "").strip()
    topic_id = data.get("topicId")
    message_id = data.get("messageId")

    if not send_user:
        return web.json_response({"code": "400", "message": "sendUserAccount is required"}, status=400)
    if topic_id is None:
        return web.json_response({"code": "400", "message": "topicId is required"}, status=400)
    if message_id is None:
        return web.json_response({"code": "400", "message": "messageId is required"}, status=400)

    # Thread aggregation: multi-turn by (user, topicId)
    thread_id = f"welink:{send_user}:{topic_id}"
    run_id = str(message_id)

    if not await registry.try_begin(thread_id, run_id):
        return web.json_response({"code": "409", "message": "busy"}, status=409)

    # WeLink SSE headers (no CORS needed for server-to-server, but harmless if present)
    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    response = web.StreamResponse(status=200, headers=headers)

    write_lock = asyncio.Lock()
    client_disconnected = False
    finished = False
    process_task: asyncio.Task | None = None

    def _welink_sse_line(payload: dict[str, Any]) -> bytes:
        return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")

    async def safe_write(payload: dict[str, Any]) -> None:
        nonlocal client_disconnected
        if client_disconnected:
            return
        async with write_lock:
            try:
                await response.write(_welink_sse_line(payload))
            except (ClientConnectionResetError, ConnectionResetError, RuntimeError):
                client_disconnected = True
                if process_task is not None and not process_task.done():
                    process_task.cancel()

    def _coerce_user_text() -> str:
        if msg_type.upper() == "IMAGE-V1":
            # MVP: degrade to text to keep the interface stable.
            # raw_content is a JSON string per PDF; keep it as-is for debugging.
            return (
                "用户发送了图片消息（暂不支持解析）。\n"
                "请用户补充文字描述或重新发送文本。\n\n"
                f"原始 content={raw_content}"
            )
        # Default: treat as plain text.
        return str(raw_content or "")

    async def _heartbeat() -> None:
        """Keepalive every ~20s to avoid WeLink idle timeout."""
        try:
            while not finished and not client_disconnected:
                await asyncio.sleep(20)
                if finished or client_disconnected:
                    break
                await safe_write({"code": "0", "isFinish": False, "data": {"type": "text", "text": ""}})
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    try:
        await response.prepare(request)

        # If agent isn't running, still return a deterministic response for smoke tests.
        if agent is None:
            await safe_write({"code": "0", "isFinish": False, "data": {"type": "text", "text": "agent not running"}})
            await safe_write({"code": "0", "isFinish": True, "data": {"type": "text", "text": ""}})
            finished = True
            return response

        user_text = _coerce_user_text()
        chunks: list[str] = []
        hb_task = asyncio.create_task(_heartbeat())
        try:
            async def on_stream(delta: str) -> None:
                if not delta:
                    return
                chunks.append(delta)
                await safe_write({"code": "0", "isFinish": False, "data": {"type": "text", "text": delta}})

            # on_progress could be mapped to planning/think later; MVP: ignore.
            process_task = asyncio.create_task(
                agent.process_direct(
                    user_text,
                    session_key=thread_id,
                    channel="welink",
                    chat_id=thread_id,
                    on_stream=on_stream,
                )
            )
            await process_task
            await safe_write({"code": "0", "isFinish": True, "data": {"type": "text", "text": ""}})
            finished = True
        finally:
            hb_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await hb_task
    except asyncio.CancelledError:
        client_disconnected = True
        if process_task is not None and not process_task.done():
            process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await process_task
        raise
    except Exception as e:
        msg = str(e) or type(e).__name__
        logger.exception("WeLink /welink/chat/stream failed: {}", msg)
        # Always send terminal frame if we can.
        await safe_write({"code": "500", "message": msg, "isFinish": True, "data": {"type": "text", "text": ""}})
        finished = True
    finally:
        await registry.end(thread_id)
        if not client_disconnected:
            with contextlib.suppress(Exception):
                await response.write_eof()

    return response


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
                        elif kind == "double_click":
                            await session.double_click(
                                float(payload.get("x_percent", 0)),
                                float(payload.get("y_percent", 0)),
                            )
                            interaction_wake.set()
                        elif kind == "get_selection":
                            text = await session.get_selection()
                            await _send_json({"type": "selection", "text": text})
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
    app.router.add_post("/api/auth/login", handle_auth_login)
    app.router.add_get("/api/auth/me", handle_auth_me)
    app.router.add_post("/api/auth/register", handle_auth_register)
    app.router.add_get("/api/admin/members", handle_admin_members_list)
    app.router.add_patch("/api/admin/members/{user_id}", handle_admin_member_patch)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/upload", handle_workspace_upload)
    app.router.add_post("/api/skill/state/sync", handle_skill_state_sync)
    app.router.add_post("/api/approve-tool", handle_approve)
    app.router.add_get("/api/task-status", handle_task_status)
    app.router.add_get("/api/file", handle_file)
    app.router.add_post("/api/config/test", handle_config_test)
    app.router.add_get("/api/remote-center/session", handle_remote_center_session)
    app.router.add_post("/api/remote-center/login", handle_remote_center_login)
    app.router.add_post("/api/remote-center/logout", handle_remote_center_logout)
    app.router.add_post("/api/remote-center/project", handle_remote_center_project)
    app.router.add_get("/api/remote-assets/org-skills", handle_remote_org_skills)
    app.router.add_get("/api/remote-assets/org-skills/{skill_id}", handle_remote_org_skill_detail)
    app.router.add_post("/api/remote-assets/org-skills/{skill_id}/import", handle_remote_org_skill_import)
    app.router.add_post("/api/remote-assets/org-skills/{skill_id}/clone-to-personal", handle_remote_org_skill_clone)
    app.router.add_get("/api/remote-assets/personal-skills", handle_personal_skills_list)
    app.router.add_post("/api/remote-assets/personal-skills/upload", handle_personal_skills_upload)
    app.router.add_get("/api/remote-assets/personal-artifacts", handle_personal_artifacts_list)
    app.router.add_post("/api/remote-assets/personal-artifacts/upload", handle_personal_artifacts_upload)
    app.router.add_post("/api/remote-assets/personal-artifacts/upload-from-session", handle_personal_artifacts_upload_from_session)
    app.router.add_get("/api/skills", handle_skills)
    app.router.add_get("/api/modules", handle_modules)
    app.router.add_post("/api/skills/publish", handle_skill_publish)
    app.router.add_post("/api/open-folder", handle_open_folder)
    app.router.add_post("/api/trash-files", handle_trash_files)
    app.router.add_get("/api/browser", handle_browser)
    app.router.add_options("/api/auth/login", handle_options)
    app.router.add_options("/api/auth/me", handle_options)
    app.router.add_options("/api/auth/register", handle_options)
    app.router.add_options("/api/admin/members", handle_options)
    app.router.add_options("/api/admin/members/{user_id}", handle_options)
    app.router.add_options("/api/chat", handle_options)
    app.router.add_options("/api/upload", handle_options)
    app.router.add_options("/api/skill/state/sync", handle_options)
    app.router.add_options("/api/approve-tool", handle_options)
    app.router.add_options("/api/task-status", handle_options)
    app.router.add_options("/api/file", handle_options)
    app.router.add_options("/api/remote-center/session", handle_options)
    app.router.add_options("/api/remote-center/login", handle_options)
    app.router.add_options("/api/remote-center/logout", handle_options)
    app.router.add_options("/api/remote-center/project", handle_options)
    app.router.add_options("/api/remote-assets/org-skills", handle_options)
    app.router.add_options("/api/remote-assets/org-skills/{skill_id}", handle_options)
    app.router.add_options("/api/remote-assets/org-skills/{skill_id}/import", handle_options)
    app.router.add_options("/api/remote-assets/org-skills/{skill_id}/clone-to-personal", handle_options)
    app.router.add_options("/api/remote-assets/personal-skills", handle_options)
    app.router.add_options("/api/remote-assets/personal-skills/upload", handle_options)
    app.router.add_options("/api/remote-assets/personal-artifacts", handle_options)
    app.router.add_options("/api/remote-assets/personal-artifacts/upload", handle_options)
    app.router.add_options("/api/remote-assets/personal-artifacts/upload-from-session", handle_options)
    app.router.add_options("/api/skills", handle_options)
    app.router.add_options("/api/modules", handle_options)
    app.router.add_options("/api/skills/publish", handle_options)
    app.router.add_options("/api/open-folder", handle_options)
    app.router.add_options("/api/trash-files", handle_options)
    app.router.add_get("/api/config", handle_config_get)
    app.router.add_post("/api/config", handle_config_post)
    app.router.add_get("/api/runtime", handle_runtime_get)
    app.router.add_get("/api/providers", handle_providers_list)
    app.router.add_post("/welink/chat/stream", handle_welink_chat_stream)
    app.router.add_options("/api/config", handle_options)
    app.router.add_options("/api/config/test", handle_options)
    app.router.add_options("/api/runtime", handle_options)
    app.router.add_options("/api/providers", handle_options)
    app.router.add_options("/welink/chat/stream", handle_options)
