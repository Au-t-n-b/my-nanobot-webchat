"""P1 tests: Hermes Structured Audit Events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_change_store import (
    AuditEvent,
    SkillChangeStore,
    _build_input_hash,
    _redact,
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


# ── Tests ─────────────────────────────────────────────────────────────────

class TestAuditTableSchema:

    def test_audit_table_created_on_init(self, tmp_path: Path):
        """hermes_audit_events table and indexes exist after store init."""
        store = _make_store(tmp_path)
        db_path = tmp_path / "skill_change_requests.db"

        with sqlite3.connect(str(db_path)) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "hermes_audit_events" in tables

            indexes = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()}
            assert "idx_ae_event_type" in indexes
            assert "idx_ae_request_id" in indexes
            assert "idx_ae_skill_name" in indexes
            assert "idx_ae_created_at" in indexes

    def test_audit_event_to_dict(self, tmp_path: Path):
        """AuditEvent.to_dict returns all __slots__ keys."""
        store = _make_store(tmp_path)
        store.record_audit_event(event_type="test", skill_name="my-skill", confidence=0.9)
        events = store.list_audit_events()
        assert len(events) == 1
        d = events[0].to_dict()
        for slot in AuditEvent.__slots__:
            assert slot in d


class TestRecordAndList:

    def test_record_and_list_basic(self, tmp_path: Path):
        """record_audit_event inserts, list_audit_events retrieves."""
        store = _make_store(tmp_path)
        store.record_audit_event(
            event_type="judge_called",
            request_id="req-123",
            skill_name="ci-pipeline",
            session_key="sess-abc",
            decision="same_duplicate",
            confidence=0.92,
            target_id="req-456",
            effect="merged",
            reason_zh="语义相同",
            input_hash="abc123",
            metadata={"extra": "data"},
        )

        events = store.list_audit_events()
        assert len(events) == 1
        e = events[0]
        assert e.event_type == "judge_called"
        assert e.request_id == "req-123"
        assert e.skill_name == "ci-pipeline"
        assert e.session_key == "sess-abc"
        assert e.decision == "same_duplicate"
        assert e.confidence == 0.92
        assert e.target_id == "req-456"
        assert e.effect == "merged"
        assert e.reason_zh == "语义相同"
        assert e.input_hash == "abc123"
        assert json.loads(e.metadata_json) == {"extra": "data"}

    def test_list_audit_events_filters(self, tmp_path: Path):
        """list_audit_events filters by request_id, skill_name, event_type, limit."""
        store = _make_store(tmp_path)
        store.record_audit_event(event_type="judge_called", request_id="r1", skill_name="skill-a")
        store.record_audit_event(event_type="judge_blacklist_hit", request_id="r2", skill_name="skill-b")
        store.record_audit_event(event_type="judge_called", request_id="r3", skill_name="skill-a")

        assert len(store.list_audit_events(request_id="r1")) == 1
        assert len(store.list_audit_events(skill_name="skill-a")) == 2
        assert len(store.list_audit_events(event_type="judge_blacklist_hit")) == 1
        assert len(store.list_audit_events(limit=2)) == 2
        # Combined filter
        assert len(store.list_audit_events(skill_name="skill-a", event_type="judge_called")) == 2

    def test_list_audit_events_by_request(self, tmp_path: Path):
        """Filtering by request_id returns only matching events."""
        store = _make_store(tmp_path)
        store.record_audit_event(event_type="judge_called", request_id="req-A", skill_name="s1")
        store.record_audit_event(event_type="judge_called", request_id="req-B", skill_name="s2")
        store.record_audit_event(event_type="enhanced_pending_created", request_id="req-A", skill_name="s1")

        events_a = store.list_audit_events(request_id="req-A")
        assert len(events_a) == 2
        assert all(e.request_id == "req-A" for e in events_a)

        events_b = store.list_audit_events(request_id="req-B")
        assert len(events_b) == 1
        assert events_b[0].request_id == "req-B"


class TestFailureIsolation:

    def test_audit_event_write_failure_does_not_break_main_flow(self, tmp_path: Path):
        """If DB write fails, record_audit_event returns None silently."""
        store = _make_store(tmp_path)
        # Corrupt the DB path to force write failure
        store._db_path = tmp_path / "nonexistent" / "subdir" / "bad.db"

        # Should not raise
        store.record_audit_event(event_type="judge_called", skill_name="test")

        # Verify we can still use the store normally after
        store._db_path = tmp_path / "skill_change_requests.db"
        req = store.create_request(
            action="create", skill_name="recovery-test",
            reason="test", proposed_content=_skill_md("recovery-test"),
        )
        assert req.status == "pending"


class TestRedaction:

    def test_audit_event_redacts_sensitive_error_message(self, tmp_path: Path):
        """reason_zh and error_message are redacted and truncated."""
        store = _make_store(tmp_path)
        long_reason = "api_key=sk-abc123def456 " * 100  # ~2400 chars with sensitive data
        long_error = "Bearer token=secret123 " * 100

        store.record_audit_event(
            event_type="judge_blacklist_hit",
            skill_name="test",
            reason_zh=long_reason,
            error_message=long_error,
        )

        events = store.list_audit_events()
        assert len(events) == 1
        e = events[0]

        # Should be truncated to 500 chars
        assert len(e.reason_zh) <= 500
        assert len(e.error_message) <= 500

        # Sensitive values should be redacted
        assert "sk-abc123def456" not in e.reason_zh
        assert "sk-abc123" in e.reason_zh or "***" in e.reason_zh
        assert "secret123" not in e.error_message
        assert "***" in e.error_message


class TestDecisionPoints:

    def test_audit_event_recorded_for_blacklist_block(self, tmp_path: Path):
        """blacklist_hit with conf>=0.85 records judge_blacklist_hit audit event."""
        store = _make_store(tmp_path)
        req = store.create_request(
            action="create", skill_name="bad-skill",
            reason="Bad idea",
            proposed_content=_skill_md("bad-skill"),
            judge_result={
                "decision": "blacklist_hit",
                "confidence": 0.92,
                "target_id": "bl-1",
                "reason_zh": "被黑名单拦截",
            },
        )
        assert req.status == "blocked_by_blacklist"

        events = store.list_audit_events(event_type="judge_blacklist_hit")
        assert len(events) == 1
        e = events[0]
        assert e.skill_name == "bad-skill"
        assert e.decision == "blacklist_hit"
        assert e.confidence == 0.92
        assert e.effect == "blocked"
        assert e.reason_zh == "被黑名单拦截"

    def test_audit_event_recorded_for_duplicate_merge(self, tmp_path: Path):
        """same_duplicate decision records judge_same_duplicate audit event."""
        store = _make_store(tmp_path)

        # Create the original pending
        original = store.create_request(
            action="create", skill_name="ci-pipeline",
            reason="CI pipeline",
            proposed_content=_skill_md("ci-pipeline"),
        )
        assert original.status == "pending"

        # Create a duplicate that will be merged
        merged = store.create_request(
            action="create", skill_name="ci-pipeline",
            reason="CI pipeline v2",
            proposed_content=_skill_md("ci-pipeline"),
            judge_result={
                "decision": "same_duplicate",
                "confidence": 0.88,
                "target_id": original.id,
                "reason_zh": "重复的CI请求",
            },
        )
        assert merged.status == "merged_with_existing"

        events = store.list_audit_events(event_type="judge_same_duplicate")
        assert len(events) == 1
        e = events[0]
        assert e.skill_name == "ci-pipeline"
        assert e.decision == "same_duplicate"
        assert e.confidence == 0.88
        assert e.effect == "merged"
        assert e.target_id == original.id

    @pytest.mark.asyncio
    async def test_audit_event_recorded_for_generate_enhanced_failure(self, tmp_path: Path):
        """generate_enhanced_candidate failure records error audit event."""
        store = _make_store(tmp_path)

        # Create a pending request
        req = store.create_request(
            action="create", skill_name="ci-pipeline",
            reason="CI",
            proposed_content=_skill_md("ci-pipeline"),
        )

        # Call generate_enhanced_candidate without provider LLM responses
        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[],
        )
        # merge_brief will fail since provider returns MagicMock
        assert result["status"] == "error"

        events = store.list_audit_events(request_id=req.id)
        assert len(events) >= 1
        # Should have at least one error event
        error_events = [e for e in events if e.error_code is not None]
        assert len(error_events) >= 1

    def test_audit_event_recorded_for_disk_conflict(self, tmp_path: Path):
        """check_disk_conflict followed by audit event recording."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"

        # Create skill on disk
        _create_skill_on_disk(skills_dir, "my-skill", _skill_md("my-skill", "Original"))

        # Create a patch request
        req = store.create_request(
            action="patch", skill_name="my-skill",
            reason="Update rule",
            old_string="Rule 1",
            new_string="Rule 1 (updated)",
        )

        # Modify the file
        import time
        time.sleep(0.05)
        (skills_dir / "my-skill" / "SKILL.md").write_text(
            _skill_md("my-skill", "Changed"), encoding="utf-8"
        )

        conflict = store.check_disk_conflict(req)
        assert conflict is not None

        # Simulate what routes.py does: record audit on conflict
        store.record_audit_event(
            event_type="approve_disk_conflict",
            request_id=req.id,
            skill_name=req.skill_name,
            effect="blocked",
            error_message=conflict,
        )

        events = store.list_audit_events(event_type="approve_disk_conflict")
        assert len(events) == 1
        e = events[0]
        assert e.request_id == req.id
        assert e.effect == "blocked"
        assert "已被修改" in e.error_message


class TestInputHash:

    def test_build_input_hash_deterministic(self):
        """Same inputs produce same hash."""
        h1 = _build_input_hash("create", "my-skill", "some reason")
        h2 = _build_input_hash("create", "my-skill", "some reason")
        assert h1 == h2
        assert len(h1) == 16

    def test_build_input_hash_differs_for_different_inputs(self):
        """Different inputs produce different hashes."""
        h1 = _build_input_hash("create", "skill-a", "reason")
        h2 = _build_input_hash("create", "skill-b", "reason")
        assert h1 != h2


# ── E2E Smoke: 5 audit scenarios ─────────────────────────────────────────

_MINIMAL_CHANGE_SUMMARY = (
    "---change_summary---\n"
    '{"preserved_points": [], "added_points": ["规则"], "changed_points": [], "ignored_points": []}\n'
    "---end_change_summary---"
)


class TestAuditSmoke:

    @pytest.mark.asyncio
    async def test_smoke_same_duplicate_produces_audit(self, tmp_path: Path):
        """same_duplicate merge → audit event with effect=merged."""
        store = _make_store(tmp_path)

        # Create original pending
        original = store.create_request(
            action="create", skill_name="ci-pipeline",
            reason="CI 流水线",
            proposed_content=_skill_md("ci-pipeline"),
        )
        assert original.status == "pending"

        # Create duplicate — judge says same_duplicate
        merged = store.create_request(
            action="create", skill_name="ci-pipeline",
            reason="CI 流水线配置",
            proposed_content=_skill_md("ci-pipeline", "CI v2"),
            judge_result={
                "decision": "same_duplicate",
                "confidence": 0.90,
                "target_id": original.id,
                "reason_zh": "语义相同的 CI 请求",
            },
        )
        assert merged.status == "merged_with_existing"

        events = store.list_audit_events(event_type="judge_same_duplicate")
        assert len(events) == 1
        assert events[0].effect == "merged"
        assert events[0].confidence == 0.90
        assert events[0].target_id == original.id

    def test_smoke_blacklist_block_produces_audit(self, tmp_path: Path):
        """blacklist_hit conf≥0.85 → audit event with effect=blocked."""
        store = _make_store(tmp_path)

        req = store.create_request(
            action="create", skill_name="spam-skill",
            reason="垃圾内容",
            proposed_content=_skill_md("spam-skill"),
            judge_result={
                "decision": "blacklist_hit",
                "confidence": 0.93,
                "target_id": "bl-1",
                "reason_zh": "被黑名单拦截",
            },
        )
        assert req.status == "blocked_by_blacklist"

        events = store.list_audit_events(event_type="judge_blacklist_hit")
        assert len(events) == 1
        assert events[0].effect == "blocked"
        assert events[0].confidence == 0.93

    @pytest.mark.asyncio
    async def test_smoke_change_summary_missing_produces_audit(self, tmp_path: Path):
        """generate-enhanced with LLM returning no change_summary → audit: change_summary_missing."""
        store = _make_store(tmp_path)

        req = store.create_request(
            action="create", skill_name="ci-pipeline",
            reason="CI",
            proposed_content=_skill_md("ci-pipeline"),
        )

        # Stage 1: brief says yes
        brief_resp = MagicMock()
        brief_resp.content = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "新规则", "source": "canonical"}],
            "ignored_points": [], "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True, "summary_zh": "值得增强",
        })
        # Stage 2: LLM returns SKILL.md WITHOUT change_summary
        gen_resp = MagicMock()
        gen_resp.content = _skill_md("ci-pipeline")

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id, selected_event_ids=[], other_extra="",
        )
        assert result["status"] == "error"

        events = store.list_audit_events(event_type="change_summary_missing",
                                          request_id=req.id)
        assert len(events) == 1
        assert events[0].error_code == "missing"

    def test_smoke_disk_conflict_produces_audit(self, tmp_path: Path):
        """approve with disk conflict → audit: approve_disk_conflict."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"
        _create_skill_on_disk(skills_dir, "my-skill", _skill_md("my-skill", "Original"))

        req = store.create_request(
            action="patch", skill_name="my-skill",
            reason="Update", old_string="Rule 1", new_string="Rule 1 v2",
        )

        # Modify file on disk
        import time
        time.sleep(0.05)
        (skills_dir / "my-skill" / "SKILL.md").write_text(
            _skill_md("my-skill", "Changed"), encoding="utf-8"
        )

        conflict = store.check_disk_conflict(req)
        assert conflict is not None
        store.record_audit_event(
            event_type="approve_disk_conflict", request_id=req.id,
            skill_name=req.skill_name, effect="blocked", error_message=conflict,
        )

        events = store.list_audit_events(event_type="approve_disk_conflict")
        assert len(events) == 1
        assert events[0].effect == "blocked"

    def test_smoke_approve_success_produces_audit(self, tmp_path: Path):
        """approve with apply success → audit: approve_apply_success."""
        store = _make_store(tmp_path)
        skills_dir = tmp_path / "skills"

        req = store.create_request(
            action="create", skill_name="new-skill",
            reason="New", proposed_content=_skill_md("new-skill"),
        )
        assert req.status == "pending"

        # Apply and approve
        from nanobot.agent.tools.skill_manage import apply_create
        result = apply_create(req.skill_name, req.proposed_content or "", skills_dir)
        assert result["success"] is True

        store.approve_request(req.id)
        store.record_audit_event(
            event_type="approve_apply_success", request_id=req.id,
            skill_name=req.skill_name, effect="approved",
        )

        events = store.list_audit_events(event_type="approve_apply_success")
        assert len(events) == 1
        assert events[0].effect == "approved"
        assert events[0].skill_name == "new-skill"

        # Verify skill exists on disk
        assert (skills_dir / "new-skill" / "SKILL.md").exists()
