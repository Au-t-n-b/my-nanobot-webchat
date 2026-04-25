"""Local JSON persistence for MVP auth/membership (``users.json`` in the registry dir).

Default location: ``~/.nanobot/workspace/registry`` (stable per user, not tied to repo cwd).
Override with env ``NANOBOT_REGISTRY_DIR`` (tests, CI, or project-local registry).

All writes are atomic (tmp + replace) and guarded by an in-process asyncio lock.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bcrypt


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_registry_dir() -> Path:
    """Per-user default: ``~/.nanobot/workspace/registry`` (e.g. Windows under the user profile)."""
    return Path.home() / ".nanobot" / "workspace" / "registry"


def registry_dir() -> Path:
    """Directory containing ``users.json`` and (with JWT) ``jwt_secret.txt``.

    * If ``NANOBOT_REGISTRY_DIR`` is set — use that (tests, sandboxes, custom layout).
    * Otherwise — :func:`default_registry_dir` (persistent home path, not repo-relative).
    """
    p = (os.environ.get("NANOBOT_REGISTRY_DIR") or "").strip()
    if p:
        return Path(p)
    return default_registry_dir()


_LOCK = asyncio.Lock()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    try:
        j = json.loads(raw)
        return j if isinstance(j, dict) else {}
    except json.JSONDecodeError:
        return {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{secrets.token_hex(6)}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _bcrypt_hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def _bcrypt_check_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


@dataclass(frozen=True)
class PublicUser:
    userId: str
    workId: str
    realName: str
    roleCode: str
    status: int
    lastLoginAt: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "userId": self.userId,
            "workId": self.workId,
            "realName": self.realName,
            "roleCode": self.roleCode,
            "status": self.status,
            "lastLoginAt": self.lastLoginAt,
        }


def ensure_seed_users(reg: Path | None = None) -> None:
    """Ensure registry has a seed ADMIN account: test/test."""
    reg = reg or registry_dir()
    users_path = reg / "users.json"
    doc = _read_json(users_path)
    users = doc.get("users")
    if not isinstance(users, list):
        users = []
    if any(isinstance(u, dict) and str(u.get("employeeNo") or "").strip() == "test" for u in users):
        return
    now = _now_iso()
    seed = {
        "id": f"u_{secrets.token_urlsafe(10)}",
        "employeeNo": "test",
        "realName": "Test Admin",
        "passwordHash": _bcrypt_hash_password("test"),
        "roleCode": "ADMIN",
        "status": 1,
        "lastLoginAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    users.append(seed)
    _atomic_write_json(
        users_path,
        {
            "schemaVersion": 1,
            "updatedAt": now,
            "users": users,
        },
    )


def read_users(reg: Path | None = None) -> list[dict[str, Any]]:
    reg = reg or registry_dir()
    ensure_seed_users(reg)
    doc = _read_json(reg / "users.json")
    users = doc.get("users")
    return users if isinstance(users, list) else []


def write_users(users: list[dict[str, Any]], reg: Path | None = None) -> None:
    reg = reg or registry_dir()
    _atomic_write_json(reg / "users.json", {"schemaVersion": 1, "updatedAt": _now_iso(), "users": users})


def find_user_by_work_id(work_id: str, *, reg: Path | None = None) -> dict[str, Any] | None:
    wid = work_id.strip()
    if not wid:
        return None
    for u in read_users(reg):
        if not isinstance(u, dict):
            continue
        if str(u.get("employeeNo") or "").strip() == wid:
            return u
    return None


def find_user_by_id(user_id: str, *, reg: Path | None = None) -> dict[str, Any] | None:
    uid = user_id.strip()
    if not uid:
        return None
    for u in read_users(reg):
        if not isinstance(u, dict):
            continue
        if str(u.get("id") or "").strip() == uid:
            return u
    return None


def public_user_from_row(row: dict[str, Any]) -> dict[str, Any]:
    from nanobot.web.local_jwt import account_role_to_api, role_code_to_api

    rc = str(row.get("roleCode") or "").strip()
    return {
        "userId": str(row.get("id") or ""),
        "workId": str(row.get("employeeNo") or "").strip(),
        "realName": str(row.get("realName") or "").strip(),
        "roleCode": rc,
        "role": role_code_to_api(rc),
        "accountRole": account_role_to_api(rc),
        "status": int(row.get("status") or 0),
        "lastLoginAt": row.get("lastLoginAt"),
    }


def write_current_login_snapshot(
    *,
    user_row: dict[str, Any],
    ip: str | None = None,
    user_agent: str | None = None,
    reg: Path | None = None,
) -> None:
    """Persist the last successful login snapshot under the registry dir.

    File: ``current_login.json`` (overwritten on each successful login).
    Note: This is a "last login" record, not a durable multi-session store.
    """
    reg = reg or registry_dir()
    _atomic_write_json(
        reg / "current_login.json",
        {
            "schemaVersion": 1,
            "updatedAt": _now_iso(),
            "ip": (ip or "").strip() or None,
            "userAgent": (user_agent or "").strip() or None,
            "user": public_user_from_row(user_row),
        },
    )


def authenticate_user(work_id: str, password: str, *, reg: Path | None = None) -> dict[str, Any] | None:
    u = find_user_by_work_id(work_id, reg=reg)
    if not u:
        return None
    if int(u.get("status") or 0) != 1:
        return None
    hashed = str(u.get("passwordHash") or "")
    if not _bcrypt_check_password(password, hashed):
        return None
    return u


def create_user(
    *,
    work_id: str,
    real_name: str,
    password: str,
    role_code: str,
    reg: Path | None = None,
) -> dict[str, Any]:
    reg = reg or registry_dir()
    wid = work_id.strip()
    rn = real_name.strip()
    if not wid or not rn:
        raise ValueError("workId and realName are required")
    if wid.lower() == "admin":
        raise ValueError("workId admin is reserved")
    if find_user_by_work_id(wid, reg=reg):
        raise ValueError("workId already exists")
    now = _now_iso()
    u = {
        "id": f"u_{secrets.token_urlsafe(10)}",
        "employeeNo": wid,
        "realName": rn,
        "passwordHash": _bcrypt_hash_password(password),
        "roleCode": role_code,
        "status": 1,
        "lastLoginAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    users = read_users(reg)
    users.append(u)
    write_users(users, reg)
    return u


def touch_last_login(user_id: str, *, reg: Path | None = None) -> None:
    reg = reg or registry_dir()
    users = read_users(reg)
    now = _now_iso()
    changed = False
    for u in users:
        if not isinstance(u, dict):
            continue
        if str(u.get("id") or "") == user_id:
            u["lastLoginAt"] = now
            u["updatedAt"] = now
            changed = True
            break
    if changed:
        write_users(users, reg)


def read_project_members(reg: Path | None = None) -> list[dict[str, Any]]:
    reg = reg or registry_dir()
    doc = _read_json(reg / "project_members.json")
    items = doc.get("members")
    return items if isinstance(items, list) else []


def write_project_members(items: list[dict[str, Any]], reg: Path | None = None) -> None:
    reg = reg or registry_dir()
    _atomic_write_json(reg / "project_members.json", {"schemaVersion": 1, "updatedAt": _now_iso(), "members": items})


def upsert_project_member(
    *,
    project_id: str,
    user_id: str,
    stages: list[str],
    invited_by: str | None,
    reg: Path | None = None,
) -> dict[str, Any]:
    reg = reg or registry_dir()
    pid = project_id.strip()
    uid = user_id.strip()
    if not pid or not uid:
        raise ValueError("projectId and userId are required")
    now = _now_iso()
    items = read_project_members(reg)
    for m in items:
        if not isinstance(m, dict):
            continue
        if str(m.get("projectId") or "") == pid and str(m.get("userId") or "") == uid:
            m["stages"] = list(stages)
            m["updatedAt"] = now
            write_project_members(items, reg)
            return m
    m = {
        "projectId": pid,
        "userId": uid,
        "stages": list(stages),
        "memberRole": "viewer",
        "memberStatus": "active",
        "invitedBy": invited_by,
        "createdAt": now,
        "updatedAt": now,
    }
    items.append(m)
    write_project_members(items, reg)
    return m


async def locked(fn, *args, **kwargs):
    async with _LOCK:
        return fn(*args, **kwargs)

