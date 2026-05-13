"""Skill management tool — create, edit, patch, delete agent skills."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool

# ── Constants ────────────────────────────────────────────────────────────────

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CONTENT_CHARS = 100_000  # ~36k tokens

VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _validate_name(name: str) -> str | None:
    if not name:
        return "Skill name is required."
    if len(name) > MAX_NAME_LENGTH:
        return f"Skill name exceeds {MAX_NAME_LENGTH} characters."
    if not VALID_NAME_RE.match(name):
        return (
            f"Invalid skill name '{name}'. Use lowercase letters, numbers, "
            "hyphens, dots, and underscores. Must start with a letter or digit."
        )
    return None


def _validate_frontmatter(content: str) -> str | None:
    if not content.strip():
        return "Content cannot be empty."
    if not content.startswith("---"):
        return "SKILL.md must start with YAML frontmatter (---)."
    end = re.search(r"\n---\s*\n", content[3:])
    if not end:
        return "SKILL.md frontmatter is not closed. Add a closing '---' line."
    yaml_text = content[3 : end.start() + 3]
    # Simple check for required fields (no yaml dep)
    if "name:" not in yaml_text:
        return "Frontmatter must include 'name' field."
    if "description:" not in yaml_text:
        return "Frontmatter must include 'description' field."
    body = content[end.end() + 3 :].strip()
    if not body:
        return "SKILL.md must have content after the frontmatter."
    return None


def _validate_content_size(content: str) -> str | None:
    if len(content) > MAX_SKILL_CONTENT_CHARS:
        return (
            f"SKILL.md is {len(content):,} chars (limit {MAX_SKILL_CONTENT_CHARS:,}). "
            "Split into a smaller SKILL.md with supporting files."
        )
    return None


def _atomic_write_text(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".skill_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _find_skill(name: str, skills_dir: Path) -> dict[str, Any] | None:
    """Find a skill by name under *skills_dir*."""
    target = skills_dir / name
    if target.is_dir() and (target / "SKILL.md").exists():
        return {"name": name, "path": target}
    return None


# ── Actions ──────────────────────────────────────────────────────────────────


def _create_skill(name: str, content: str, skills_dir: Path) -> dict[str, Any]:
    err = _validate_name(name)
    if err:
        return {"success": False, "error": err}
    err = _validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}
    err = _validate_content_size(content)
    if err:
        return {"success": False, "error": err}
    existing = _find_skill(name, skills_dir)
    if existing:
        return {"success": False, "error": f"Skill '{name}' already exists at {existing['path']}."}
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(skill_dir / "SKILL.md", content)
    return {
        "success": True,
        "message": f"Skill '{name}' created.",
        "path": str(skill_dir),
    }


def _edit_skill(name: str, content: str, skills_dir: Path) -> dict[str, Any]:
    err = _validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}
    err = _validate_content_size(content)
    if err:
        return {"success": False, "error": err}
    existing = _find_skill(name, skills_dir)
    if not existing:
        return {"success": False, "error": f"Skill '{name}' not found."}
    skill_md = existing["path"] / "SKILL.md"
    original = skill_md.read_text(encoding="utf-8") if skill_md.exists() else None
    _atomic_write_text(skill_md, content)
    return {"success": True, "message": f"Skill '{name}' updated.", "path": str(existing["path"])}


def _patch_skill(
    name: str,
    old_string: str,
    new_string: str,
    skills_dir: Path,
    replace_all: bool = False,
) -> dict[str, Any]:
    if not old_string:
        return {"success": False, "error": "old_string is required for patch."}
    if new_string is None:
        return {"success": False, "error": "new_string is required for patch."}
    existing = _find_skill(name, skills_dir)
    if not existing:
        return {"success": False, "error": f"Skill '{name}' not found."}
    target = existing["path"] / "SKILL.md"
    if not target.exists():
        return {"success": False, "error": f"SKILL.md not found for skill '{name}'."}
    content = target.read_text(encoding="utf-8")
    count = content.count(old_string)
    if count == 0:
        preview = content[:500] + ("..." if len(content) > 500 else "")
        return {"success": False, "error": "old_string not found in SKILL.md.", "preview": preview}
    if count > 1 and not replace_all:
        return {
            "success": False,
            "error": f"old_string matches {count} locations. Set replace_all=true or use a more specific string.",
        }
    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    err = _validate_frontmatter(new_content)
    if err:
        return {"success": False, "error": f"Patch would break SKILL.md structure: {err}"}
    _atomic_write_text(target, new_content)
    return {
        "success": True,
        "message": f"Patched SKILL.md in skill '{name}' ({count} replacement{'s' if count > 1 else ''}).",
    }


def _delete_skill(name: str, skills_dir: Path) -> dict[str, Any]:
    existing = _find_skill(name, skills_dir)
    if not existing:
        return {"success": False, "error": f"Skill '{name}' not found."}
    shutil.rmtree(existing["path"])
    return {"success": True, "message": f"Skill '{name}' deleted."}


# ── Tool class ───────────────────────────────────────────────────────────────


class SkillManageTool(Tool):
    """Create, edit, patch, or delete agent skills (SKILL.md)."""

    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._skills_dir = workspace / "skills"

    @property
    def name(self) -> str:
        return "skill_manage"

    @property
    def description(self) -> str:
        return (
            "Manage agent skills (SKILL.md files). Actions:\n"
            "- create: Create a new skill with full SKILL.md content (YAML frontmatter + markdown body).\n"
            "- edit: Full rewrite of an existing skill's SKILL.md.\n"
            "- patch: Targeted find-and-replace within SKILL.md.\n"
            "- delete: Remove a skill entirely.\n\n"
            "Use create when: complex task succeeded (5+ tool calls), errors overcome, "
            "non-trivial workflow discovered, or user asks to remember a procedure.\n"
            "Use patch when: a skill has missing steps, wrong commands, or needs pitfalls added."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "edit", "patch", "delete"],
                    "description": "Action to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Skill name (lowercase, hyphens, digits).",
                },
                "content": {
                    "type": "string",
                    "description": "Full SKILL.md content for create/edit (must have YAML frontmatter with name + description).",
                },
                "old_string": {
                    "type": "string",
                    "description": "Text to find for patch action.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text for patch action.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences for patch (default false).",
                },
            },
            "required": ["action", "name"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        skills_dir = self._skills_dir

        if action == "create":
            content = kwargs.get("content", "")
            return _create_skill(name, content, skills_dir)
        elif action == "edit":
            content = kwargs.get("content", "")
            return _edit_skill(name, content, skills_dir)
        elif action == "patch":
            old_string = kwargs.get("old_string", "")
            new_string = kwargs.get("new_string", "")
            replace_all = kwargs.get("replace_all", False)
            return _patch_skill(name, old_string, new_string, skills_dir, replace_all)
        elif action == "delete":
            return _delete_skill(name, skills_dir)
        else:
            return {"success": False, "error": f"Unknown action '{action}'. Use create/edit/patch/delete."}
