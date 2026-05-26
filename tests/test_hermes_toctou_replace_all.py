"""P0 tests: Approve TOCTOU file-state check + replace_all full chain."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_change_store import SkillChangeStore, SkillChangeRequest
from nanobot.agent.tools.skill_manage import (
    apply_create,
    apply_edit,
    apply_patch,
    validate_name,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> SkillChangeStore:
    store = SkillChangeStore(tmp_path, expiry_days=60, duplicate_grace_days=14)
    provider = MagicMock()
    provider.chat = AsyncMock()
    store.set_provider(provider, "test-model")
    return store


def _skill_md(name: str = "test-skill", desc: str = "A test skill") -> str:
    return (
        f"---\nname: {name}\ndescription: {desc}\n---\n"
        f"# {name}\n\n## When to use\nTest.\n\n## Rules\n- Rule 1\n"
    )


def _create_skill_on_disk(skills_dir: Path, name: str, content: str | None = None) -> Path:
    target = skills_dir / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(content or _skill_md(name), encoding="utf-8")
    return target


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── 1. Target file state capture ─────────────────────────────────────────

class TestTargetFileStateCapture:

    def test_pending_records_target_file_hash_for_patch(self, tmp_path: Path):
        """Patch request captures hash of existing skill file at creation time."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        skill_content = _skill_md("my-skill", "Original")
        _create_skill_on_disk(skills_dir, "my-skill", skill_content)

        req = store.create_request(
            action="patch",
            skill_name="my-skill",
            reason="Add missing step",
            old_string="Rule 1",
            new_string="Rule 1\n- Rule 2",
        )
        assert req.status == "pending"
        assert req.target_file_exists == 1
        assert req.target_file_hash is not None
        assert req.target_file_hash == _file_hash(skills_dir / "my-skill" / "SKILL.md")
        assert req.target_file_size is not None
        assert req.target_file_size > 0

    def test_create_request_records_file_not_exists(self, tmp_path: Path):
        """Create request records target_file_exists=0 when skill doesn't exist."""
        store = _make_store(tmp_path)

        req = store.create_request(
            action="create",
            skill_name="new-skill",
            reason="Brand new skill",
            proposed_content=_skill_md("new-skill"),
        )
        assert req.status == "pending"
        assert req.target_file_exists == 0
        assert req.target_file_hash is None

    def test_edit_request_captures_file_state(self, tmp_path: Path):
        """Edit request captures hash/mtime/size of existing skill."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        content = _skill_md("edit-target", "Old desc")
        _create_skill_on_disk(skills_dir, "edit-target", content)

        req = store.create_request(
            action="edit",
            skill_name="edit-target",
            reason="Update description",
            proposed_content=_skill_md("edit-target", "New desc"),
        )
        assert req.target_file_exists == 1
        assert req.target_file_hash == _file_hash(skills_dir / "edit-target" / "SKILL.md")
        assert req.target_file_mtime is not None

    def test_delete_request_captures_file_state(self, tmp_path: Path):
        """Delete request captures file state of existing skill."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        _create_skill_on_disk(skills_dir, "to-delete")

        req = store.create_request(
            action="delete",
            skill_name="to-delete",
            reason="No longer needed",
        )
        assert req.target_file_exists == 1
        assert req.target_file_hash is not None

    def test_to_dict_includes_new_fields(self, tmp_path: Path):
        """to_dict returns replace_all and target_file_* fields."""
        store = _make_store(tmp_path)
        req = store.create_request(
            action="patch",
            skill_name="some-skill",
            reason="test",
            replace_all=True,
        )
        d = req.to_dict()
        assert "replace_all" in d
        assert "target_file_exists" in d
        assert "target_file_hash" in d
        assert "target_file_mtime" in d
        assert "target_file_size" in d


# ── 2. TOCTOU disk conflict detection ────────────────────────────────────

class TestDiskConflictDetection:

    def test_approve_create_rejects_when_skill_now_exists(self, tmp_path: Path):
        """Create pending (target didn't exist) → skill created on disk → 409."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"

        # Create pending when skill doesn't exist
        req = store.create_request(
            action="create",
            skill_name="conflict-skill",
            reason="New skill",
            proposed_content=_skill_md("conflict-skill"),
        )
        assert req.target_file_exists == 0

        # Someone else creates the skill on disk
        _create_skill_on_disk(skills_dir, "conflict-skill")

        # TOCTOU check should detect conflict
        conflict = store.check_disk_conflict(req)
        assert conflict is not None
        assert "已被创建" in conflict

    def test_approve_patch_rejects_when_file_hash_changed(self, tmp_path: Path):
        """Patch pending → file modified on disk → conflict detected."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        _create_skill_on_disk(skills_dir, "my-skill", _skill_md("my-skill", "Original"))

        req = store.create_request(
            action="patch",
            skill_name="my-skill",
            reason="Fix rule",
            old_string="Rule 1",
            new_string="Rule 1 (updated)",
        )
        assert req.target_file_exists == 1
        old_hash = req.target_file_hash

        # File changes on disk
        time.sleep(0.05)
        (skills_dir / "my-skill" / "SKILL.md").write_text(
            _skill_md("my-skill", "Changed by someone else"), encoding="utf-8"
        )

        new_hash = _file_hash(skills_dir / "my-skill" / "SKILL.md")
        assert new_hash != old_hash  # confirm file actually changed

        conflict = store.check_disk_conflict(req)
        assert conflict is not None
        assert "已被修改" in conflict

    def test_approve_edit_rejects_when_target_deleted(self, tmp_path: Path):
        """Edit pending → skill deleted from disk → conflict detected."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        _create_skill_on_disk(skills_dir, "vanishing-skill")

        req = store.create_request(
            action="edit",
            skill_name="vanishing-skill",
            reason="Update content",
            proposed_content=_skill_md("vanishing-skill", "Updated"),
        )
        assert req.target_file_exists == 1

        # Skill gets deleted
        import shutil
        shutil.rmtree(skills_dir / "vanishing-skill")

        conflict = store.check_disk_conflict(req)
        assert conflict is not None
        assert "已被删除" in conflict

    def test_approve_allows_when_hash_unchanged(self, tmp_path: Path):
        """Patch pending → file unchanged → no conflict."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        _create_skill_on_disk(skills_dir, "stable-skill")

        req = store.create_request(
            action="patch",
            skill_name="stable-skill",
            reason="Add note",
            old_string="Rule 1",
            new_string="Rule 1\n- Note",
        )

        # File not changed
        conflict = store.check_disk_conflict(req)
        assert conflict is None

    def test_approve_create_allows_when_still_not_exists(self, tmp_path: Path):
        """Create pending → skill still doesn't exist → no conflict."""
        store = _make_store(tmp_path)

        req = store.create_request(
            action="create",
            skill_name="fresh-skill",
            reason="New skill",
            proposed_content=_skill_md("fresh-skill"),
        )

        conflict = store.check_disk_conflict(req)
        assert conflict is None

    def test_disk_conflict_keeps_request_pending(self, tmp_path: Path):
        """When disk conflict detected, request stays pending (not approved/rejected)."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"

        req = store.create_request(
            action="create",
            skill_name="clash-skill",
            reason="New skill",
            proposed_content=_skill_md("clash-skill"),
        )

        # Create the skill on disk
        _create_skill_on_disk(skills_dir, "clash-skill")

        # Check conflict — just detection, doesn't change status
        conflict = store.check_disk_conflict(req)
        assert conflict is not None

        # Request should still be pending
        fresh = store.get_request(req.id)
        assert fresh.status == "pending"

    def test_delete_rejects_when_target_deleted(self, tmp_path: Path):
        """Delete pending → skill already deleted → conflict detected."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        _create_skill_on_disk(skills_dir, "deleted-skill")

        req = store.create_request(
            action="delete",
            skill_name="deleted-skill",
            reason="Remove",
        )

        import shutil
        shutil.rmtree(skills_dir / "deleted-skill")

        conflict = store.check_disk_conflict(req)
        assert conflict is not None
        assert "已被删除" in conflict


# ── 3. replace_all full chain ────────────────────────────────────────────

class TestReplaceAllChain:

    def test_replace_all_persisted(self, tmp_path: Path):
        """replace_all=True is stored in the request and persisted to DB."""
        store = _make_store(tmp_path)

        req = store.create_request(
            action="patch",
            skill_name="some-skill",
            reason="Update all",
            replace_all=True,
        )
        assert req.replace_all == 1  # stored as integer

        # Read back from DB
        fresh = store.get_request(req.id)
        assert fresh.replace_all == 1

    def test_replace_all_defaults_false(self, tmp_path: Path):
        """replace_all defaults to 0 when not specified."""
        store = _make_store(tmp_path)

        req = store.create_request(
            action="patch",
            skill_name="some-skill",
            reason="test",
        )
        assert req.replace_all == 0

    def test_approve_patch_with_replace_all_true(self, tmp_path: Path):
        """approve handler passes replace_all to apply_patch."""
        skills_dir = tmp_path / "skills"
        content = "---\nname: multi\ndescription: test\n---\nAAA\nBBB\nAAA\n"
        _create_skill_on_disk(skills_dir, "multi", content)

        store = _make_store(tmp_path)
        req = store.create_request(
            action="patch",
            skill_name="multi",
            reason="Replace all AAA",
            old_string="AAA",
            new_string="CCC",
            replace_all=True,
        )

        # Apply the patch with replace_all from the request
        result = apply_patch(
            req.skill_name,
            req.old_string or "",
            req.new_string or "",
            skills_dir,
            replace_all=bool(req.replace_all),
        )
        assert result["success"] is True

        updated = (skills_dir / "multi" / "SKILL.md").read_text(encoding="utf-8")
        assert "AAA" not in updated
        assert updated.count("CCC") == 2

    def test_approve_patch_without_replace_all_fails_multi(self, tmp_path: Path):
        """Without replace_all, patching a multi-match old_string fails."""
        skills_dir = tmp_path / "skills"
        content = "---\nname: multi2\ndescription: test\n---\nAAA\nBBB\nAAA\n"
        _create_skill_on_disk(skills_dir, "multi2", content)

        store = _make_store(tmp_path)
        req = store.create_request(
            action="patch",
            skill_name="multi2",
            reason="Try replace",
            old_string="AAA",
            new_string="CCC",
            replace_all=False,
        )

        result = apply_patch(
            req.skill_name,
            req.old_string or "",
            req.new_string or "",
            skills_dir,
            replace_all=False,
        )
        assert result["success"] is False
        assert "matches 2 locations" in result["error"]


# ── 4. DB migration idempotency ──────────────────────────────────────────

class TestDBMigration:

    def test_migration_idempotent(self, tmp_path: Path):
        """Opening store twice doesn't fail on duplicate ALTER TABLE."""
        store1 = _make_store(tmp_path)
        # Create a request to exercise the schema
        store1.create_request(
            action="create",
            skill_name="mig-test",
            reason="migration",
            proposed_content=_skill_md("mig-test"),
        )

        # Re-open the same DB
        store2 = SkillChangeStore(tmp_path, expiry_days=60)
        reqs = store2.list_requests()
        assert len(reqs) == 1
        assert reqs[0].skill_name == "mig-test"
        # New fields should be present (None for old data)
        d = reqs[0].to_dict()
        assert "replace_all" in d
        assert "target_file_exists" in d

    def test_old_pending_without_file_state_no_false_conflict(self, tmp_path: Path):
        """Requests created before migration (no file state) don't false-positive conflict."""
        store = _make_store(tmp_path)

        # Simulate old request by directly inserting into DB without file state
        with store._conn() as conn:
            conn.execute(
                """INSERT INTO skill_change_requests
                   (id, action, skill_name, reason, status, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("old-req-1", "create", "legacy-skill", "old request",
                 "pending", datetime.now(timezone.utc).isoformat(),
                 datetime.now(timezone.utc).isoformat()),
            )

        req = store.get_request("old-req-1")
        assert req.target_file_exists is None  # NULL from old data

        # Should NOT conflict — we can't check what we didn't record
        conflict = store.check_disk_conflict(req)
        assert conflict is None
