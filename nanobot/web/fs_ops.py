"""Filesystem operations for AGUI sidebar APIs."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


class FsOpError(Exception):
    code = "internal_error"
    status = 500

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class BadRequestError(FsOpError):
    code = "bad_request"
    status = 400


class NotFoundError(FsOpError):
    code = "not_found"
    status = 404


def get_workspace_root() -> Path:
    override = os.environ.get("NANOBOT_AGUI_WORKSPACE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".nanobot" / "workspace").resolve()


def resolve_in_workspace(target: str, *, must_exist: bool = True) -> Path:
    if not isinstance(target, str) or not target.strip():
        raise BadRequestError("target is required")
    workspace = get_workspace_root()
    raw = Path(target.strip()).expanduser()
    joined = raw if raw.is_absolute() else workspace / raw
    resolved = joined.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as e:
        raise BadRequestError("path escapes workspace") from e
    if must_exist and not resolved.exists():
        raise NotFoundError("target not found")
    return resolved


def open_in_os(target: Path) -> None:
    sys_name = platform.system()
    if sys_name == "Windows":
        if target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            subprocess.Popen(["explorer", str(target)])
        return
    if sys_name == "Darwin":
        subprocess.Popen(["open", str(target.parent if target.is_file() else target)])
        return
    subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])


def trash_paths(raw_paths: list[str]) -> dict[str, object]:
    """Trash paths under workspace; escape path causes whole request rejection."""
    if not isinstance(raw_paths, list) or not raw_paths:
        raise BadRequestError("paths must be a non-empty array")

    # Validate all first (all-or-nothing on escape).
    resolved: list[Path] = []
    seen: set[str] = set()
    for raw in raw_paths:
        p = resolve_in_workspace(str(raw), must_exist=False)
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(p)

    try:
        from send2trash import send2trash
    except Exception as e:  # pragma: no cover
        raise FsOpError("send2trash is not available", detail=str(e)) from e

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for p in resolved:
        if not p.exists():
            failed.append({"path": str(p), "reason": "not found"})
            continue
        try:
            send2trash(str(p))
            deleted.append(str(p))
        except Exception as e:
            failed.append({"path": str(p), "reason": str(e)})

    return {"ok": len(failed) == 0, "deleted": deleted, "failed": failed}

