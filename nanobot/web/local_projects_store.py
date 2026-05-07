"""Local JSON persistence for projects (registry-backed, MVP).

File: ``projects.json`` under :func:`nanobot.web.local_json_store.registry_dir`.

This is a minimal project entity store to close the loop:
- PD can create projects
- ADMIN can list all projects
- PD can only list projects they created (owner)
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanobot.web.local_json_store import _atomic_write_json, _read_json, registry_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def projects_file(reg: Path | None = None) -> Path:
    reg = reg or registry_dir()
    return reg / "projects.json"


def read_projects(reg: Path | None = None) -> list[dict[str, Any]]:
    doc = _read_json(projects_file(reg))
    items = doc.get("projects")
    return items if isinstance(items, list) else []


def write_projects(items: list[dict[str, Any]], reg: Path | None = None) -> None:
    _atomic_write_json(projects_file(reg), {"schemaVersion": 1, "updatedAt": _now_iso(), "projects": items})


def create_project(
    *,
    owner_user_id: str,
    name: str,
    profile: dict[str, Any] | None = None,
    reg: Path | None = None,
) -> dict[str, Any]:
    reg = reg or registry_dir()
    owner = (owner_user_id or "").strip()
    nm = (name or "").strip()
    if not owner:
        raise ValueError("ownerUserId is required")
    if not nm:
        raise ValueError("name is required")

    now = _now_iso()
    pid = f"p_{secrets.token_urlsafe(10)}"
    prof = profile if isinstance(profile, dict) else {}
    proj = {
        "projectId": pid,
        "name": nm,
        "ownerUserId": owner,
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
        "profile": prof,
    }
    items = read_projects(reg)
    items.append(proj)
    write_projects(items, reg)
    return proj

