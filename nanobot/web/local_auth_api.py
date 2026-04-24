"""Auth HTTP handlers backed by local JSON registry (MVP).

Endpoints:
- POST /api/auth/login (public)
- GET /api/auth/me (Bearer)
- POST /api/auth/register (Bearer; ADMIN registers PD; PD registers EMPLOYEE + stages by project)
"""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from nanobot.web.local_json_store import (
    authenticate_user,
    create_user,
    locked,
    public_user_from_row,
    touch_last_login,
    upsert_project_member,
)
from nanobot.web.local_jwt import account_role_to_api, ensure_jwt_secret_key_runtime, sign_token

STAGE_ENUM = {
    "作业管理",
    "智慧工勘",
    "建模仿真",
    "系统设计",
    "设备安装",
    "软件部署与调测",
}


def _json_error(detail: str, status: int) -> web.Response:
    return web.json_response({"detail": detail}, status=status)


def _auth_account_role(request: web.Request) -> str:
    au = request.get("auth_user") or {}
    if isinstance(au, dict):
        return str(au.get("accountRole") or "").strip().lower()
    return ""


async def handle_auth_login(request: web.Request) -> web.Response:
    ensure_jwt_secret_key_runtime()
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return _json_error("请求体须为 JSON", 400)
    if not isinstance(data, dict):
        return _json_error("请求体须为 JSON 对象", 400)

    work_id = str(data.get("workId") or "").strip()
    password = str(data.get("password") or "")
    if not work_id or not password:
        return _json_error("workId 与 password 为必填项", 400)

    u = await locked(authenticate_user, work_id, password)
    if not u:
        return _json_error("账号或密码不正确", 401)

    await locked(touch_last_login, str(u.get("id") or ""))
    token = sign_token(user_row=u)
    return web.json_response({"token": token, "user": public_user_from_row(u)})


async def handle_auth_me(request: web.Request) -> web.Response:
    au = request.get("auth_user")
    if not isinstance(au, dict):
        return _json_error("未登录", 401)
    # Returning token payload is fine; also include a public user snapshot.
    user_id = str(au.get("userId") or "").strip()
    if not user_id:
        return _json_error("未登录", 401)
    # best-effort: store may have updated fields
    from nanobot.web.local_json_store import find_user_by_id

    row = await locked(find_user_by_id, user_id)
    return web.json_response({"user": public_user_from_row(row) if isinstance(row, dict) else au})


async def handle_auth_register(request: web.Request) -> web.Response:
    """ADMIN registers PD; PD registers EMPLOYEE members with project stages."""
    ensure_jwt_secret_key_runtime()
    role = _auth_account_role(request)
    if role not in ("admin", "pd"):
        return _json_error("仅系统管理员或 PD 可新增账号", 403)

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return _json_error("请求体须为 JSON", 400)
    if not isinstance(data, dict):
        return _json_error("请求体须为 JSON 对象", 400)

    work_id = str(data.get("workId") or "").strip()
    password = str(data.get("password") or "")
    password_confirm = str(data.get("passwordConfirm") or "")
    real_name = str(data.get("realName") or "").strip()
    if not work_id or not real_name or not password:
        return _json_error("workId、realName、password 为必填项", 400)
    if password != password_confirm:
        return _json_error("两次输入的密码不一致", 400)
    if len(password) < 8:
        return _json_error("密码长度至少 8 位", 400)

    if role == "admin":
        role_code = str(data.get("roleCode") or "EMPLOYEE").strip().upper()
        if role_code not in ("PD", "EMPLOYEE"):
            return _json_error("roleCode 仅支持 PD 或 EMPLOYEE", 400)
        try:
            u = await locked(
                create_user,
                work_id=work_id,
                real_name=real_name,
                password=password,
                role_code=role_code,
            )
        except ValueError as e:
            return _json_error(str(e), 409)
        return web.json_response({"user": public_user_from_row(u)}, status=201)

    # PD path: must create EMPLOYEE + bind stages by projectId
    project_id = str(data.get("projectId") or "").strip()
    raw_stages = data.get("stages")
    if not project_id:
        return _json_error("projectId 为必填项（PD 注册成员必须绑定项目）", 400)
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

    try:
        u = await locked(
            create_user,
            work_id=work_id,
            real_name=real_name,
            password=password,
            role_code="EMPLOYEE",
        )
    except ValueError as e:
        return _json_error(str(e), 409)

    auth_u = request.get("auth_user") if isinstance(request.get("auth_user"), dict) else {}
    invited_by = str(auth_u.get("userId") or "").strip() or None
    member = await locked(
        upsert_project_member,
        project_id=project_id,
        user_id=str(u.get("id") or ""),
        stages=stages,
        invited_by=invited_by,
    )
    return web.json_response({"user": public_user_from_row(u), "member": member}, status=201)

