"""Projects API backed by local registry JSON (MVP).

Endpoints:
- GET /api/projects (ADMIN sees all; PD sees own; others forbidden)
- POST /api/projects (PD creates; ADMIN optionally allowed)
"""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from nanobot.web.local_json_store import locked
from nanobot.web.local_projects_store import create_project, read_projects


def _json_error(detail: str, status: int) -> web.Response:
    return web.json_response({"detail": detail}, status=status)


def _auth_user(request: web.Request) -> dict[str, Any]:
    au = request.get("auth_user") or {}
    return au if isinstance(au, dict) else {}


def _account_role(request: web.Request) -> str:
    au = _auth_user(request)
    return str(au.get("accountRole") or "").strip().lower()


def _user_id(request: web.Request) -> str:
    au = _auth_user(request)
    return str(au.get("userId") or "").strip()


async def handle_projects_list(request: web.Request) -> web.Response:
    role = _account_role(request)
    if role not in ("admin", "pd"):
        return _json_error("无权限", 403)
    uid = _user_id(request)
    if not uid:
        return _json_error("未登录", 401)

    items = await locked(read_projects)
    out: list[dict[str, Any]] = []
    for p in items:
        if not isinstance(p, dict):
            continue
        if role == "admin" or str(p.get("ownerUserId") or "") == uid:
            out.append(p)
    # stable ordering: newest first
    out.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)
    return web.json_response({"projects": out})


async def handle_projects_create(request: web.Request) -> web.Response:
    role = _account_role(request)
    if role not in ("admin", "pd"):
        return _json_error("无权限", 403)
    uid = _user_id(request)
    if not uid:
        return _json_error("未登录", 401)

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return _json_error("请求体须为 JSON", 400)
    if not isinstance(data, dict):
        return _json_error("请求体须为 JSON 对象", 400)
    name = str(data.get("name") or "").strip()
    if not name:
        return _json_error("name 为必填项", 400)
    profile_raw = data.get("profile")
    profile = profile_raw if isinstance(profile_raw, dict) else {}
    project_code = str(profile.get("projectCode") or "").strip()
    scenario = str(profile.get("scenario") or "").strip()
    if not project_code:
        return _json_error("profile.projectCode 为必填项", 400)
    if not scenario:
        return _json_error("profile.scenario 为必填项", 400)

    # Normalize optional fields (MVP): store null/[] when missing.
    scale = str(profile.get("scale") or "").strip() or None
    start_date = str(profile.get("startDate") or "").strip() or None
    site_ready = str(profile.get("siteReadyDate") or "").strip() or None
    delivery_tags_raw = profile.get("deliveryTags")
    delivery_tags = (
        [str(x).strip() for x in delivery_tags_raw if str(x).strip()]
        if isinstance(delivery_tags_raw, list)
        else []
    )
    profile_norm = {
        "projectCode": project_code,
        "scenario": scenario,
        "scale": scale,
        "startDate": start_date,
        "siteReadyDate": site_ready,
        "deliveryTags": delivery_tags,
    }

    try:
        proj = await locked(create_project, owner_user_id=uid, name=name, profile=profile_norm)
    except ValueError as e:
        return _json_error(str(e), 400)
    return web.json_response({"project": proj}, status=201)

