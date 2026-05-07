"""JWT helpers for local JSON auth MVP."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

TOKEN_EXPIRE_DAYS = 7


def _secret_path() -> Path:
    from nanobot.web.local_json_store import registry_dir

    return registry_dir() / "jwt_secret.txt"


def ensure_jwt_secret_key_runtime() -> str:
    """Ensure JWT secret exists (``JWT_SECRET_KEY`` env, else file next to users.json in ``registry_dir()``)."""
    cur = (os.environ.get("JWT_SECRET_KEY") or "").strip()
    if cur:
        return cur
    p = _secret_path()
    if p.exists():
        s = p.read_text(encoding="utf-8").strip()
        if s:
            os.environ["JWT_SECRET_KEY"] = s
            return s
    p.parent.mkdir(parents=True, exist_ok=True)
    s = secrets.token_urlsafe(48)
    p.write_text(s, encoding="utf-8")
    os.environ["JWT_SECRET_KEY"] = s
    return s


def role_code_to_api(role_code: str | None) -> str:
    c = (role_code or "").strip().upper()
    return "pd" if c in ("ADMIN", "PD") else "user"


def account_role_to_api(role_code: str | None) -> str:
    c = (role_code or "").strip().upper()
    if c == "ADMIN":
        return "admin"
    if c == "PD":
        return "pd"
    return "employee"


def sign_token(*, user_row: dict[str, Any]) -> str:
    secret = ensure_jwt_secret_key_runtime()
    now = datetime.now(timezone.utc)
    uid = str(user_row.get("id") or "")
    emp = str(user_row.get("employeeNo") or "").strip()
    real = str(user_row.get("realName") or "").strip()
    role_code = str(user_row.get("roleCode") or "")
    payload = {
        "userId": uid,
        "workId": emp,
        "name": real or emp,
        "nickname": "",
        "realName": real,
        "role": role_code_to_api(role_code),
        "accountRole": account_role_to_api(role_code),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=TOKEN_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str) -> dict[str, Any]:
    secret = ensure_jwt_secret_key_runtime()
    return jwt.decode(token, secret, algorithms=["HS256"])

