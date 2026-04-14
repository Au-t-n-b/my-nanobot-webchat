"""Load declarative skill manifests from workspace skills."""

from __future__ import annotations

import json

from nanobot.skills.manifest_schema import SkillManifest, parse_skill_manifest
from nanobot.web.skills import get_skill_dir


def load_skill_manifest(skill_name: str) -> SkillManifest:
    skill_dir = get_skill_dir(skill_name)
    path = skill_dir / "skill.manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"skill.manifest.json missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("skill.manifest.json must be a JSON object")
    return parse_skill_manifest(raw)
