"""Skill management tool — create, edit, patch, delete agent skills.

All actions create pending requests (via SkillChangeStore) instead of
writing files directly.  Requests are applied only when approved through
the review UI (POST /api/skill-requests/{id}/approve).
"""

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.skill_change_store import SkillChangeStore
from nanobot.agent.tools.base import Tool

# ── Constants ────────────────────────────────────────────────────────────────

MAX_NAME_LENGTH = 64
MAX_SKILL_CONTENT_CHARS = 100_000  # ~36k tokens

VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


# ── Helpers (used by routes.py approve handler too) ──────────────────────────


def validate_name(name: str) -> str | None:
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


def validate_frontmatter(content: str) -> str | None:
    if not content.strip():
        return "Content cannot be empty."
    if not content.startswith("---"):
        return "SKILL.md must start with YAML frontmatter (---)."
    end = re.search(r"\n---\s*\n", content[3:])
    if not end:
        return "SKILL.md frontmatter is not closed. Add a closing '---' line."
    yaml_text = content[3 : end.start() + 3]
    if "name:" not in yaml_text:
        return "Frontmatter must include 'name' field."
    if "description:" not in yaml_text:
        return "Frontmatter must include 'description' field."
    body = content[end.end() + 3 :].strip()
    if not body:
        return "SKILL.md must have content after the frontmatter."
    return None


def validate_content_size(content: str) -> str | None:
    if len(content) > MAX_SKILL_CONTENT_CHARS:
        return (
            f"SKILL.md is {len(content):,} chars (limit {MAX_SKILL_CONTENT_CHARS:,}). "
            "Split into a smaller SKILL.md with supporting files."
        )
    return None


def resolve_skill_target(skills_dir: Path, name: str) -> tuple[Path, str | None]:
    """Validate skill name and resolve to an absolute path within skills_dir.

    Returns (target_path, error_message).  error_message is None on success.
    """
    err = validate_name(name)
    if err:
        return Path(), err
    root = skills_dir.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        return Path(), f"Path traversal blocked: '{name}' resolves outside skills directory."
    return target, None


# ── File-system actions (called by approve handler) ──────────────────────────


def apply_create(name: str, content: str, skills_dir: Path) -> dict[str, Any]:
    import os
    import tempfile

    target, err = resolve_skill_target(skills_dir, name)
    if err:
        return {"success": False, "error": err}
    err = validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}
    err = validate_content_size(content)
    if err:
        return {"success": False, "error": err}
    if target.is_dir() and (target / "SKILL.md").exists():
        return {"success": False, "error": f"Skill '{name}' already exists."}
    target.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target), prefix=".skill_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(target / "SKILL.md"))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"success": True, "message": f"Skill '{name}' created.", "path": str(target)}


def apply_edit(name: str, content: str, skills_dir: Path) -> dict[str, Any]:
    import os
    import tempfile

    target, err = resolve_skill_target(skills_dir, name)
    if err:
        return {"success": False, "error": err}
    err = validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}
    err = validate_content_size(content)
    if err:
        return {"success": False, "error": err}
    if not (target.is_dir() and (target / "SKILL.md").exists()):
        return {"success": False, "error": f"Skill '{name}' not found."}
    skill_md = target / "SKILL.md"
    fd, tmp = tempfile.mkstemp(dir=str(target), prefix=".skill_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(skill_md))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"success": True, "message": f"Skill '{name}' updated.", "path": str(target)}


def apply_patch(
    name: str,
    old_string: str,
    new_string: str,
    skills_dir: Path,
    replace_all: bool = False,
) -> dict[str, Any]:
    import os
    import tempfile

    target, err = resolve_skill_target(skills_dir, name)
    if err:
        return {"success": False, "error": err}
    if not old_string:
        return {"success": False, "error": "old_string is required for patch."}
    if new_string is None:
        return {"success": False, "error": "new_string is required for patch."}
    if not (target.is_dir() and (target / "SKILL.md").exists()):
        return {"success": False, "error": f"Skill '{name}' not found."}
    skill_md = target / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    count = content.count(old_string)
    if count == 0:
        return {"success": False, "error": "old_string not found in SKILL.md."}
    if count > 1 and not replace_all:
        return {
            "success": False,
            "error": f"old_string matches {count} locations. Set replace_all=true or use a more specific string.",
        }
    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    err = validate_frontmatter(new_content)
    if err:
        return {"success": False, "error": f"Patch would break SKILL.md structure: {err}"}
    fd, tmp = tempfile.mkstemp(dir=str(target), prefix=".skill_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp, str(skill_md))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {
        "success": True,
        "message": f"Patched SKILL.md in skill '{name}' ({count} replacement{'s' if count > 1 else ''}).",
    }


def apply_delete(name: str, skills_dir: Path) -> dict[str, Any]:
    import shutil

    target, err = resolve_skill_target(skills_dir, name)
    if err:
        return {"success": False, "error": err}
    if not (target.is_dir() and (target / "SKILL.md").exists()):
        return {"success": False, "error": f"Skill '{name}' not found."}
    shutil.rmtree(target)
    return {"success": True, "message": f"Skill '{name}' deleted."}


# ── Tool class ───────────────────────────────────────────────────────────────


class SkillManageTool(Tool):
    """Create, edit, patch, or delete agent skills (SKILL.md) — pending review."""

    _ALL_ACTIONS = ["create", "edit", "patch", "delete"]

    def __init__(
        self,
        workspace: Path,
        change_store: SkillChangeStore,
        session_key: str = "",
        trigger_conversation: str = "",
        allowed_actions: set[str] | None = None,
    ):
        self._workspace = workspace
        self._skills_dir = workspace / "skills"
        self._change_store = change_store
        self._session_key = session_key
        self._trigger_conversation = trigger_conversation
        self._allowed_actions = allowed_actions

    @property
    def name(self) -> str:
        return "skill_manage"

    @property
    def description(self) -> str:
        if self._allowed_actions == {"create"}:
            return (
                "Create a new agent skill (SKILL.md).\n"
                "Only 'create' action is available. Provide full SKILL.md content "
                "(YAML frontmatter with name + description, then markdown body).\n"
                "All changes create a pending review request, applied only after user approval."
            )
        return (
            "Manage agent skills (SKILL.md files). Actions:\n"
            "- create: Create a new skill with full SKILL.md content (YAML frontmatter + markdown body).\n"
            "- edit: Full rewrite of an existing skill's SKILL.md.\n"
            "- patch: Targeted find-and-replace within SKILL.md.\n"
            "- delete: Remove a skill entirely.\n\n"
            "All changes create a pending review request. The change is applied only after user approval.\n"
            "Use create when: complex task succeeded (5+ tool calls), errors overcome, "
            "non-trivial workflow discovered, or user asks to remember a procedure.\n"
            "Use patch when: a skill has missing steps, wrong commands, or needs pitfalls added."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        action_enum = list(self._allowed_actions) if self._allowed_actions else self._ALL_ACTIONS
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": action_enum,
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
                "reason": {
                    "type": "string",
                    "description": "Why this skill change is needed (required for all actions).",
                },
            },
            "required": ["action", "name", "reason"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        reason = kwargs.get("reason", "")

        # Hard guard: enforce allowed_actions if set
        if self._allowed_actions is not None and action not in self._allowed_actions:
            return {"success": False, "error": f"Action '{action}' is not allowed in this context."}

        if not reason.strip():
            return {"success": False, "error": "reason is required for all skill changes."}

        # Validate name and resolve path for all actions
        _, name_err = resolve_skill_target(self._skills_dir, name)
        if name_err:
            return {"success": False, "error": name_err}

        # Validate inputs before creating the request
        if action == "create":
            content = kwargs.get("content", "")
            fm_err = validate_frontmatter(content)
            if fm_err:
                return {"success": False, "error": fm_err}
            size_err = validate_content_size(content)
            if size_err:
                return {"success": False, "error": size_err}
        elif action == "edit":
            content = kwargs.get("content", "")
            fm_err = validate_frontmatter(content)
            if fm_err:
                return {"success": False, "error": fm_err}
            size_err = validate_content_size(content)
            if size_err:
                return {"success": False, "error": size_err}
        elif action == "patch":
            old_string = kwargs.get("old_string", "")
            if not old_string:
                return {"success": False, "error": "old_string is required for patch."}
        elif action == "delete":
            pass
        else:
            return {"success": False, "error": f"Unknown action '{action}'. Use create/edit/patch/delete."}

        # Pre-flight checks for edit/patch/delete: skill must exist
        if action in ("edit", "patch", "delete"):
            target = self._skills_dir / name
            if not (target.is_dir() and (target / "SKILL.md").exists()):
                return {"success": False, "error": f"Skill '{name}' not found."}

        # Create pending request (with optional LLM semantic judge)
        try:
            # Run async prefilter + LLM judge before creating the request
            judge_result = None
            coverage_result = None
            try:
                judge_result, coverage_result = await self._change_store.prefilter_and_judge(
                    action=action,
                    skill_name=name,
                    reason=reason,
                    proposed_content=kwargs.get("content"),
                    trigger_conversation=self._trigger_conversation,
                )
            except Exception as e:
                logger.debug("Prefilter/judge skipped: {}", e)
                judge_result = None
                coverage_result = None

            req = self._change_store.create_request(
                action=action,
                skill_name=name,
                reason=reason,
                trigger_session=self._session_key,
                trigger_conversation=self._trigger_conversation,
                proposed_content=kwargs.get("content"),
                old_string=kwargs.get("old_string"),
                new_string=kwargs.get("new_string"),
                replace_all=bool(kwargs.get("replace_all", False)),
                judge_result=judge_result,
                coverage_result=coverage_result,
            )

            if req.status == "blocked_by_blacklist":
                logger.info(
                    "SkillChangeStore: blocked by blacklist for '{}' (similar to existing blacklist entry)",
                    name,
                )
                return {
                    "success": True,
                    "message": f"Skill change for '{name}' blocked by blacklist rule.",
                    "status": "blocked_by_blacklist",
                }

            if req.status == "covered_by_existing":
                existing_name = name
                try:
                    ids = json.loads(req.related_existing_skill_ids or "[]")
                    if ids:
                        existing_name = ids[0]
                except (json.JSONDecodeError, TypeError):
                    pass
                logger.info(
                    "SkillChangeStore: covered by existing skill '{}' for '{}'",
                    existing_name, name,
                )
                return {
                    "success": True,
                    "message": f"已有技能「{existing_name}」已覆盖该模式，未创建新建议。",
                    "status": "covered_by_existing",
                    "existing_skill_name": existing_name,
                    "reason_zh": req.related_existing_skill_note or "",
                }

            if req.status == "merged_with_existing":
                logger.info(
                    "SkillChangeStore: merged into existing pending request for '{}' (id={}, duplicates={})",
                    name, req.id, req.duplicate_count,
                )
                return {
                    "success": True,
                    "message": f"Similar pending request already exists for '{name}' (id={req.id}, {req.duplicate_count} similar matches).",
                    "request_id": req.id,
                    "status": "merged_with_existing",
                    "duplicate_count": req.duplicate_count,
                }

            logger.info(
                "SkillChangeStore: created {} request for '{}' (id={})",
                action, name, req.id,
            )
            return {
                "success": True,
                "message": f"Skill change request created (id={req.id}). "
                           f"Awaiting user approval to {action} skill '{name}'.",
                "request_id": req.id,
                "status": "pending_review",
            }
        except Exception as e:
            logger.exception("SkillChangeStore: failed to create request")
            return {"success": False, "error": str(e)}
