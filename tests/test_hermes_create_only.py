"""P0 tests: Hermes create-only — allowed_actions, prompt, merge/enhanced guards."""

import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nanobot.agent.skill_change_store import SkillChangeStore, SkillChangeRequest
from nanobot.agent.tools.skill_manage import SkillManageTool


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(workspace=tmp_path, expiry_days=60)


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    sd = tmp_path / "skills"
    sd.mkdir()
    return sd


def _make_store_with_provider(tmp_path, decision=None, confidence=0.9):
    """Create a store with a mock LLM provider for judge calls."""
    store = SkillChangeStore(workspace=tmp_path, expiry_days=60)
    if decision is not None:
        provider = MagicMock()
        resp = MagicMock()
        resp.content = '{"decision": "' + decision + '", "confidence": ' + str(confidence) + ', "target_id": null, "reason_zh": "测试"}'
        provider.chat = MagicMock(return_value=asyncio.coroutine(lambda: resp)())
        store.set_provider(provider, "test-model")
    return store


# ── Test: SkillManageTool allowed_actions ─────────────────────────────────────


class TestAllowedActions:
    """Test that allowed_actions restricts tool schema and execute()."""

    def test_unrestricted_schema_has_all_actions(self):
        tool = SkillManageTool(
            workspace=Path("/tmp/ws"),
            change_store=MagicMock(),
        )
        params = tool.parameters
        enum = params["properties"]["action"]["enum"]
        assert set(enum) == {"create", "edit", "patch", "delete"}

    def test_create_only_schema_has_only_create(self):
        tool = SkillManageTool(
            workspace=Path("/tmp/ws"),
            change_store=MagicMock(),
            allowed_actions={"create"},
        )
        params = tool.parameters
        enum = params["properties"]["action"]["enum"]
        assert enum == ["create"]

    @pytest.mark.asyncio
    async def test_unrestricted_allows_all_actions(self, store, skills_dir):
        tool = SkillManageTool(
            workspace=skills_dir.parent,
            change_store=store,
            allowed_actions=None,
        )
        # Should not reject at the allowed_actions guard
        # (will fail for other reasons like missing skill, but not "not allowed")
        result = await tool.execute(action="create", name="test-skill", reason="test",
                                     content="---\nname: test-skill\ndescription: test\n---\nBody")
        assert "not allowed" not in str(result.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_create_only_rejects_patch(self, store, skills_dir):
        tool = SkillManageTool(
            workspace=skills_dir.parent,
            change_store=store,
            allowed_actions={"create"},
        )
        result = await tool.execute(action="patch", name="test-skill", reason="test",
                                     old_string="x", new_string="y")
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_only_rejects_edit(self, store, skills_dir):
        tool = SkillManageTool(
            workspace=skills_dir.parent,
            change_store=store,
            allowed_actions={"create"},
        )
        result = await tool.execute(action="edit", name="test-skill", reason="test",
                                     content="---\nname: test-skill\ndescription: test\n---\nBody")
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_only_rejects_delete(self, store, skills_dir):
        tool = SkillManageTool(
            workspace=skills_dir.parent,
            change_store=store,
            allowed_actions={"create"},
        )
        result = await tool.execute(action="delete", name="test-skill", reason="test")
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_only_allows_create(self, store, skills_dir):
        tool = SkillManageTool(
            workspace=skills_dir.parent,
            change_store=store,
            allowed_actions={"create"},
        )
        result = await tool.execute(action="create", name="test-skill", reason="test",
                                     content="---\nname: test-skill\ndescription: test\n---\nBody")
        assert result["success"] is True

    def test_create_only_description_mentions_only_create(self):
        tool = SkillManageTool(
            workspace=Path("/tmp/ws"),
            change_store=MagicMock(),
            allowed_actions={"create"},
        )
        desc = tool.description.lower()
        assert "create" in desc
        assert "patch" not in desc
        assert "edit" not in desc
        assert "delete" not in desc

    def test_unrestricted_description_mentions_all_actions(self):
        tool = SkillManageTool(
            workspace=Path("/tmp/ws"),
            change_store=MagicMock(),
        )
        desc = tool.description.lower()
        assert "create" in desc
        assert "patch" in desc
        assert "edit" in desc
        assert "delete" in desc


# ── Test: Hermes prompt ──────────────────────────────────────────────────────


class TestHermesPrompt:
    """Test that _run_skill_review prompt does not reference patch/edit/delete."""

    def test_prompt_does_not_reference_patch(self):
        """Verify the Hermes prompt no longer mentions patch."""
        # Read the prompt from loop.py source
        import nanobot.agent.loop as loop_mod
        src = inspect.getsource(loop_mod.AgentLoop._run_skill_review)
        # The prompt should not contain action='patch'
        assert "action='patch'" not in src
        assert 'action="patch"' not in src

    def test_prompt_mentions_create_only(self):
        """Verify the Hermes prompt says create-only."""
        import nanobot.agent.loop as loop_mod
        src = inspect.getsource(loop_mod.AgentLoop._run_skill_review)
        assert "action='create'" in src

    def test_prompt_says_no_patch_edit_delete(self):
        """Verify the Hermes prompt explicitly prohibits patch/edit/delete."""
        import nanobot.agent.loop as loop_mod
        src = inspect.getsource(loop_mod.AgentLoop._run_skill_review)
        assert "Do NOT patch, edit, or delete" in src or "do NOT patch, edit, or delete" in src


# ── Test: generate_enhanced rejects non-create ───────────────────────────────


class TestGenerateEnhancedGuard:
    """Test that generate_enhanced_candidate rejects non-create canonical requests."""

    def test_rejects_edit_action(self, store: SkillChangeStore):
        # Create an edit pending request directly in DB
        req = store.create_request(
            action="edit", skill_name="test-skill", reason="test edit",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody",
        )
        result = asyncio.get_event_loop().run_until_complete(
            store.generate_enhanced_candidate(
                target_request_id=req.id,
                selected_event_ids=[],
                other_extra="",
            )
        )
        assert result["status"] == "error"
        assert "create" in result["message"].lower() or "仅支持" in result["message"]

    def test_rejects_patch_action(self, store: SkillChangeStore):
        # Insert a patch pending request
        import json, uuid
        from datetime import datetime, timedelta, timezone
        from nanobot.agent.skill_change_store import build_similarity_key
        req_id = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=60)
        sim_key = build_similarity_key("patch", "test-skill", "test patch")
        with store._conn() as conn:
            conn.execute(
                """INSERT INTO skill_change_requests
                   (id, action, skill_name, proposed_content, old_string, new_string,
                    reason, trigger_session, trigger_conversation, status, priority,
                    conflict_ids, created_at, expires_at, reviewed_at, reviewer_note,
                    duplicate_count, last_matched_at, similarity_key, maybe_duplicate_ids,
                    related_existing_skill_ids, related_existing_skill_note, existing_coverage_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (req_id, "patch", "test-skill", None, "old", "new",
                 "test patch", "", "", "pending", 0, None,
                 now.isoformat(), expires.isoformat(), None, None,
                 0, None, sim_key, None, None, None, None),
            )
        result = asyncio.get_event_loop().run_until_complete(
            store.generate_enhanced_candidate(
                target_request_id=req_id,
                selected_event_ids=[],
                other_extra="",
            )
        )
        assert result["status"] == "error"

    def test_create_action_still_works(self, store: SkillChangeStore):
        req = store.create_request(
            action="create", skill_name="test-skill", reason="test create",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody",
        )
        # Without provider, it will fail at LLM call, but should NOT fail at action check
        result = asyncio.get_event_loop().run_until_complete(
            store.generate_enhanced_candidate(
                target_request_id=req.id,
                selected_event_ids=[],
                other_extra="",
            )
        )
        # Should NOT be "仅支持 create" error
        assert "仅支持" not in result.get("message", "")
        # Will be an error about missing provider, which is expected
        assert result["status"] == "error"


# ── Test: Duplicate merge rejects cross-action ───────────────────────────────


class TestCrossActionMergeGuard:
    """Test that _merge_into_existing rejects cross-action merges."""

    def test_different_action_types_not_merged(self, store: SkillChangeStore):
        """An edit request should not auto-merge into a create request."""
        # Create first pending with action="create"
        first = store.create_request(
            action="create", skill_name="test-skill", reason="first",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody1",
        )
        # Simulate judge returning same_duplicate for an edit request targeting the create pending
        judge_result = {
            "decision": "same_duplicate",
            "confidence": 0.95,
            "target_id": first.id,
            "reason_zh": "测试跨 action 合并",
        }
        result = store.create_request(
            action="edit", skill_name="test-skill", reason="second edit",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody2",
            judge_result=judge_result,
        )
        # Should NOT be merged_with_existing
        assert result.status != "merged_with_existing"
        # Should be a new pending (related_but_distinct fallback)
        assert result.status == "pending"
        assert result.id != "blacklisted"

    def test_same_action_duplicate_still_merges(self, store: SkillChangeStore):
        """Same action + same_duplicate decision should still merge."""
        first = store.create_request(
            action="create", skill_name="test-skill", reason="first",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody1",
        )
        judge_result = {
            "decision": "same_duplicate",
            "confidence": 0.95,
            "target_id": first.id,
            "reason_zh": "测试同 action 合并",
        }
        result = store.create_request(
            action="create", skill_name="test-skill", reason="second create",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody2",
            judge_result=judge_result,
        )
        assert result.status == "merged_with_existing"
        assert result.duplicate_count == 1

    def test_different_action_can_be_related_but_not_merged(self, store: SkillChangeStore):
        """Cross-action related_but_distinct should create new pending with maybe_duplicate_ids."""
        first = store.create_request(
            action="create", skill_name="test-skill", reason="first",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody1",
        )
        judge_result = {
            "decision": "related_but_distinct",
            "confidence": 0.85,
            "target_id": first.id,
            "reason_zh": "相关但不同",
        }
        result = store.create_request(
            action="edit", skill_name="test-skill", reason="second edit",
            proposed_content="---\nname: test-skill\ndescription: test\n---\nBody2",
            judge_result=judge_result,
        )
        assert result.status == "pending"
        import json
        maybe = json.loads(result.maybe_duplicate_ids or "[]")
        assert first.id in maybe
