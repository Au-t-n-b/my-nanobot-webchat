"""Admin/PD member management API backed by local JSON registry (MVP)."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from nanobot.web.local_auth_api import STAGE_ENUM
from nanobot.web.local_json_store import (
    find_user_by_id,
    locked,
    public_user_from_row,
    read_project_members,
    upsert_project_member,
)


def _json_error(detail: str, status: int) -> web.Response:
    return web.json_response({"detail": detail}, status=status)


def _account_role(request: web.Request) -> str:
    au = request.get("auth_user") or {}
    if isinstance(au, dict):
        return str(au.get("accountRole") or "").strip().lower()
    return ""


async def handle_admin_members_list(request: web.Request) -> web.Response:
    role = _account_role(request)
    if role not in ("admin", "pd"):
        return _json_error("无权限", 403)
    project_id = str(request.query.get("projectId") or "").strip()
    if not project_id:
        return _json_error("projectId 为必填项", 400)

    members = await locked(read_project_members)
    items = [m for m in members if isinstance(m, dict) and str(m.get("projectId") or "") == project_id]
    out: list[dict[str, Any]] = []
    for m in items:
        uid = str(m.get("userId") or "").strip()
        if not uid:
            continue
        row = await locked(find_user_by_id, uid)
        if not isinstance(row, dict):
            continue
        pu = public_user_from_row(row)
        pu["stages"] = list(m.get("stages") or [])
        out.append(pu)

    # stable-ish ordering: PD first then employees; then workId
    def _order(x: dict[str, Any]) -> tuple[int, str]:
        rc = str(x.get("roleCode") or "").upper()
        pri = 0 if rc == "PD" else 1
        return pri, str(x.get("workId") or "")

    out.sort(key=_order)
    return web.json_response({"projectId": project_id, "members": out})


async def handle_admin_member_patch(request: web.Request) -> web.Response:
    role = _account_role(request)
    if role not in ("admin", "pd"):
        return _json_error("无权限", 403)
    user_id = str(request.match_info.get("user_id") or "").strip()
    if not user_id:
        return _json_error("userId 缺失", 400)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return _json_error("请求体须为 JSON", 400)
    if not isinstance(data, dict):
        return _json_error("请求体须为 JSON 对象", 400)
    project_id = str(data.get("projectId") or "").strip()
    if not project_id:
        return _json_error("projectId 为必填项", 400)
    raw_stages = data.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        return _json_error("stages 为必填项且至少 1 项", 400)
    stages: list[str] = []
    for s in raw_stages:
        t = str(s).strip()
        if not t:
            continue
        if t not in STAGE_ENUM:
            return _json_error(f"未知阶段：{t}", 400)
        if t not in stages:
            stages.append(t)
    if not stages:
        return _json_error("stages 为必填项且至少 1 项", 400)

    # PD can only patch members already in that project.
    if role == "pd":
        members = await locked(read_project_members)
        ok = any(
            isinstance(m, dict)
            and str(m.get("projectId") or "") == project_id
            and str(m.get("userId") or "") == user_id
            for m in members
        )
        if not ok:
            return _json_error("无权限修改该项目成员", 403)

    auth_u = request.get("auth_user") if isinstance(request.get("auth_user"), dict) else {}
    invited_by = str(auth_u.get("userId") or "").strip() or None
    member = await locked(
        upsert_project_member,
        project_id=project_id,
        user_id=user_id,
        stages=stages,
        invited_by=invited_by,
    )
    row = await locked(find_user_by_id, user_id)
    pu = public_user_from_row(row) if isinstance(row, dict) else {"userId": user_id}
    pu["stages"] = list(member.get("stages") or [])
    return web.json_response({"member": pu})

