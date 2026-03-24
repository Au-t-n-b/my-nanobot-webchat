"""Skill discovery helpers for AGUI Phase 3."""

from __future__ import annotations

import os
from pathlib import Path


def get_skills_root() -> Path:
    """Return fixed skills root (test override allowed via env)."""
    override = os.environ.get("NANOBOT_AGUI_SKILLS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".nanobot" / "workspace" / "skills").resolve()


def list_skills() -> list[dict[str, object]]:
    """Scan ``<skills_root>/*/SKILL.md`` and return stable A->Z list."""
    root = get_skills_root()
    root.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, object]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.is_file():
            continue
        st = skill_file.stat()
        items.append(
            {
                "name": child.name,
                "skillDir": str(child.resolve()),
                "skillFile": str(skill_file.resolve()),
                "mtimeMs": int(st.st_mtime * 1000),
            }
        )

    items.sort(key=lambda it: str(it["name"]).lower())
    return items

