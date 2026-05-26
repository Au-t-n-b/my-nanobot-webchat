"""Tests for skill_manage path traversal protection and apply functions."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from nanobot.agent.tools.skill_manage import (
    apply_create,
    apply_delete,
    apply_edit,
    apply_patch,
    resolve_skill_target,
    validate_name,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    sd = tmp_path / "skills"
    sd.mkdir()
    return sd


_VALID_SKILL_MD = (
    "---\n"
    "name: test-skill\n"
    "description: A test skill.\n"
    "---\n"
    "# Test Skill\n\nDoes something useful.\n"
)


def _make_skill(skills_dir: Path, name: str, content: str = _VALID_SKILL_MD) -> Path:
    """Helper: create a skill directory with SKILL.md."""
    target = skills_dir / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(content, encoding="utf-8")
    return target


# ── validate_name ─────────────────────────────────────────────────────────

def test_validate_name_accepts_valid():
    assert validate_name("my-skill") is None
    assert validate_name("my_skill") is None
    assert validate_name("my.skill") is None
    assert validate_name("a") is None
    assert validate_name("skill123") is None


def test_validate_name_rejects_empty():
    assert validate_name("") is not None


def test_validate_name_rejects_uppercase():
    assert validate_name("MySkill") is not None


def test_validate_name_rejects_spaces():
    assert validate_name("my skill") is not None


def test_validate_name_rejects_slash():
    assert validate_name("my/skill") is not None


def test_validate_name_rejects_dotdot():
    assert validate_name("..") is not None


def test_validate_name_rejects_traversal():
    assert validate_name("../../etc/passwd") is not None
    assert validate_name("..\\windows\\system32") is not None


def test_validate_name_rejects_too_long():
    assert validate_name("a" * 65) is not None


# ── resolve_skill_target ─────────────────────────────────────────────────

def test_resolve_skill_target_valid(skills_dir: Path):
    target, err = resolve_skill_target(skills_dir, "my-skill")
    assert err is None
    assert target == (skills_dir / "my-skill").resolve()


def test_resolve_skill_target_blocks_traversal(skills_dir: Path):
    _, err = resolve_skill_target(skills_dir, "../etc")
    assert err is not None
    assert "traversal" in err.lower() or "invalid" in err.lower()


def test_resolve_skill_target_blocks_dotdot(skills_dir: Path):
    _, err = resolve_skill_target(skills_dir, "..")
    assert err is not None


def test_resolve_skill_target_blocks_absolute():
    tmp = Path("/tmp")
    _, err = resolve_skill_target(tmp, "/etc/passwd")
    assert err is not None


# ── apply_create ──────────────────────────────────────────────────────────

def test_apply_create_success(skills_dir: Path):
    result = apply_create("new-skill", _VALID_SKILL_MD, skills_dir)
    assert result["success"] is True
    assert (skills_dir / "new-skill" / "SKILL.md").exists()
    content = (skills_dir / "new-skill" / "SKILL.md").read_text()
    assert "test-skill" in content


def test_apply_create_rejects_duplicate(skills_dir: Path):
    _make_skill(skills_dir, "existing-skill")
    result = apply_create("existing-skill", _VALID_SKILL_MD, skills_dir)
    assert result["success"] is False
    assert "already exists" in result["error"]


def test_apply_create_rejects_traversal(skills_dir: Path):
    result = apply_create("../../etc", _VALID_SKILL_MD, skills_dir)
    assert result["success"] is False


def test_apply_create_rejects_bad_frontmatter(skills_dir: Path):
    result = apply_create("bad-skill", "no frontmatter here", skills_dir)
    assert result["success"] is False
    assert "frontmatter" in result["error"].lower()


def test_apply_create_rejects_empty_content(skills_dir: Path):
    result = apply_create("empty-skill", "", skills_dir)
    assert result["success"] is False


# ── apply_edit ────────────────────────────────────────────────────────────

def test_apply_edit_success(skills_dir: Path):
    _make_skill(skills_dir, "edit-skill")
    new_content = _VALID_SKILL_MD.replace("A test skill.", "Updated description.")
    result = apply_edit("edit-skill", new_content, skills_dir)
    assert result["success"] is True
    assert "Updated description" in (skills_dir / "edit-skill" / "SKILL.md").read_text()


def test_apply_edit_rejects_nonexistent(skills_dir: Path):
    result = apply_edit("no-such-skill", _VALID_SKILL_MD, skills_dir)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_apply_edit_rejects_traversal(skills_dir: Path):
    _make_skill(skills_dir, "some-skill")
    result = apply_edit("../../etc", _VALID_SKILL_MD, skills_dir)
    assert result["success"] is False


# ── apply_patch ───────────────────────────────────────────────────────────

def test_apply_patch_success(skills_dir: Path):
    _make_skill(skills_dir, "patch-skill")
    result = apply_patch("patch-skill", "A test skill.", "A patched skill.", skills_dir)
    assert result["success"] is True
    assert "A patched skill." in (skills_dir / "patch-skill" / "SKILL.md").read_text()


def test_apply_patch_rejects_nonexistent(skills_dir: Path):
    result = apply_patch("no-such-skill", "old", "new", skills_dir)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_apply_patch_rejects_traversal(skills_dir: Path):
    result = apply_patch("../../etc", "old", "new", skills_dir)
    assert result["success"] is False


def test_apply_patch_rejects_old_not_found(skills_dir: Path):
    _make_skill(skills_dir, "patch-skill")
    result = apply_patch("patch-skill", "NONEXISTENT_STRING", "new", skills_dir)
    assert result["success"] is False
    assert "not found" in result["error"]


# ── apply_delete ──────────────────────────────────────────────────────────

def test_apply_delete_success(skills_dir: Path):
    _make_skill(skills_dir, "delete-skill")
    result = apply_delete("delete-skill", skills_dir)
    assert result["success"] is True
    assert not (skills_dir / "delete-skill").exists()


def test_apply_delete_rejects_nonexistent(skills_dir: Path):
    result = apply_delete("no-such-skill", skills_dir)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_apply_delete_rejects_traversal(skills_dir: Path):
    result = apply_delete("../../etc", skills_dir)
    assert result["success"] is False
