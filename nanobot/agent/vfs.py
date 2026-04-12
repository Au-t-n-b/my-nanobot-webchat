"""Virtual File System (VFS) — workspace:// 路径隔离层（SDUI M2 之后的安全基建）。

设计目标：
- 将物理 workspace 目录映射为逻辑协议 workspace://
- Agent / Tool 层只处理逻辑路径；所有落盘文件操作必须经过 sandbox 校验
- 严禁通过 ../、绝对路径、盘符、UNC、反斜杠等方式访问 workspace 之外
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


class SecurityError(RuntimeError):
    """Raised when a path escapes VFS sandbox."""


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _reject_if_looks_like_windows_abs(p: str) -> None:
    # Examples: "C:\\a", "C:/a", "\\\\server\\share", "\\a\\b"
    s = (p or "").strip()
    if not s:
        return
    if s.startswith("\\\\") or s.startswith("//"):
        raise SecurityError("UNC/network paths are not allowed in workspace://")
    if s.startswith("\\") or s.startswith("/"):
        # Leading slash is absolute in posix; leading backslash behaves as absolute-ish on Windows.
        raise SecurityError("Absolute paths are not allowed in workspace://")
    if len(s) >= 2 and s[1] == ":":
        # Drive letter.
        raise SecurityError("Drive-letter paths are not allowed in workspace://")


@dataclass(frozen=True, slots=True)
class VirtualFileSystem:
    """A strict sandboxed VFS rooted at a physical workspace directory."""

    workspace_root: Path
    scheme: str = "workspace://"

    def __post_init__(self) -> None:
        root = Path(self.workspace_root).expanduser()
        # Resolve to collapse symlinks; workspace itself may be a symlink, but we lock on its resolved target.
        object.__setattr__(self, "workspace_root", root.resolve())

    # ──────────────────────────────────────────────────────────────────
    # Path mapping
    # ──────────────────────────────────────────────────────────────────
    def is_logical_path(self, path: str) -> bool:
        return str(path or "").strip().startswith(self.scheme)

    def to_logical(self, physical: str | Path) -> str:
        """Map a physical path to workspace://... (only if inside workspace)."""
        p = Path(physical).expanduser()
        resolved = p.resolve()
        root = self.workspace_root
        if not _is_relative_to(resolved, root):
            raise SecurityError(f"Path is outside workspace: {resolved}")
        rel = resolved.relative_to(root)
        # Force posix separators in protocol.
        rel_posix = PurePosixPath(*rel.parts).as_posix()
        return f"{self.scheme}{rel_posix}"

    def to_physical(self, logical: str) -> Path:
        """Map workspace://... to a physical Path (sandboxed)."""
        rel = self._parse_workspace_logical(logical)
        # Build candidate path and resolve to defeat symlink-escape attempts.
        root = self.workspace_root
        candidate = (root / Path(*rel.parts)).resolve()
        if not _is_relative_to(candidate, root):
            raise SecurityError("Path escape detected (outside workspace)")
        return candidate

    # ──────────────────────────────────────────────────────────────────
    # Validation helpers
    # ──────────────────────────────────────────────────────────────────
    def validate_logical(self, logical: str) -> None:
        """Validate that logical path is workspace:// and cannot escape the sandbox."""
        _ = self.to_physical(logical)

    def ensure_under_workspace(self, physical: str | Path) -> Path:
        """Validate a physical path is within workspace_root and return resolved path."""
        p = Path(physical).expanduser().resolve()
        if not _is_relative_to(p, self.workspace_root):
            raise SecurityError(f"Path is outside workspace: {p}")
        return p

    # ──────────────────────────────────────────────────────────────────
    # Internal parsing
    # ──────────────────────────────────────────────────────────────────
    def _parse_workspace_logical(self, logical: str) -> PurePosixPath:
        raw = str(logical or "").strip()
        if not raw.startswith(self.scheme):
            raise SecurityError(f"Only {self.scheme} paths are allowed")

        rest = raw[len(self.scheme) :].strip()
        # Empty maps to workspace root.
        if rest == "":
            return PurePosixPath(".")

        # Protocol must be posix-like: forward slashes only.
        if "\\" in rest:
            raise SecurityError("Backslashes are not allowed in workspace:// paths")

        _reject_if_looks_like_windows_abs(rest)

        # Normalize: strip leading "./" and leading "/" (absolute is already rejected).
        while rest.startswith("./"):
            rest = rest[2:]

        p = PurePosixPath(rest)

        # Lexical sandbox: reject parent traversal and weird empty segments.
        for part in p.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise SecurityError("Parent traversal '..' is not allowed in workspace://")
        return p

    # ──────────────────────────────────────────────────────────────────
    # Convenience (optional for tool layer)
    # ──────────────────────────────────────────────────────────────────
    def join(self, *logical_parts: str) -> str:
        """Join logical path segments under workspace:// (no leading slashes)."""
        parts: list[str] = []
        for seg in logical_parts:
            s = str(seg or "").strip()
            if not s:
                continue
            if s.startswith(self.scheme):
                s = s[len(self.scheme) :]
            if "\\" in s:
                raise SecurityError("Backslashes are not allowed in workspace:// paths")
            _reject_if_looks_like_windows_abs(s)
            parts.append(s.strip("/"))
        joined = "/".join([p for p in parts if p])
        # Re-parse to enforce full sandbox rules.
        self.validate_logical(f"{self.scheme}{joined}" if joined else f"{self.scheme}")
        return f"{self.scheme}{joined}" if joined else f"{self.scheme}"

    def iter_dir(self, logical_dir: str) -> Iterable[str]:
        """List a directory and return workspace:// paths (best-effort utility)."""
        d = self.to_physical(logical_dir)
        if not d.exists() or not d.is_dir():
            return []
        out: list[str] = []
        for child in d.iterdir():
            try:
                out.append(self.to_logical(child))
            except SecurityError:
                # Shouldn't happen because child comes from within, but keep strict.
                continue
        return out

