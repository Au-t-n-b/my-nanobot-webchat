"""Path normalization and resolution for ``GET /api/file`` (spec §4.6, D6)."""

from __future__ import annotations

from pathlib import Path


def normalize_file_query(raw: str) -> str:
    """Backslashes → slashes; strip control characters (incl. ``\\r``, ``\\n``)."""
    if not raw:
        return ""
    s = raw.replace("\\", "/")
    s = "".join(ch for ch in s if ord(ch) >= 32)
    return s.strip()


def resolve_file_target(normalized: str, workspace_root: Path) -> Path:
    """Absolute paths: resolve as-is (D6). Relative: under ``workspace_root`` only."""
    if not normalized or normalized == ".":
        raise ValueError("empty path")
    workspace_root = workspace_root.resolve()
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate.resolve()
    joined = (workspace_root / candidate).resolve()
    try:
        joined.relative_to(workspace_root)
    except ValueError as e:
        raise ValueError("path escapes workspace") from e
    return joined
