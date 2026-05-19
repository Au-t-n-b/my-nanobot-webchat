"""P0.5 tests: Generate-enhanced Conservation Law + change_summary_zh."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_change_store import (
    SkillChangeStore,
    SkillChangeRequest,
    _MERGE_GENERATE_PROMPT,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> SkillChangeStore:
    store = SkillChangeStore(tmp_path, expiry_days=60)
    return store


def _make_request(store: SkillChangeStore, **overrides) -> SkillChangeRequest:
    defaults = {
        "action": "create",
        "skill_name": "ci-pipeline",
        "reason": "CI pipeline skill",
        "proposed_content": (
            "---\nname: ci-pipeline\ndescription: CI 流水线\n---\n"
            "## When to use\nCI 场景\n\n## Rules\n- 规则1: 必须通过测试\n- 规则2: 禁止直接 push\n"
        ),
    }
    defaults.update(overrides)
    return store.create_request(**defaults)


def _make_event(store: SkillChangeStore, target_id: str) -> str:
    """Insert a duplicate event and return its ID."""
    evt = store.create_duplicate_event(
        target_request_id=target_id,
        candidate_data={
            "skill_name": "ci-pipeline",
            "reason": "CI pipeline v2",
            "trigger_conversation": "",
            "proposed_content": "---\nname: ci-pipeline\ndescription: CI v2\n---\n## When to use\nCI\n## Rules\n- v2 rule",
        },
        judge_result={"confidence": 0.9, "reason_zh": "相似"},
    )
    return evt.id


def _mock_provider_with_responses(*contents: str):
    """Create a mock provider that returns multiple responses sequentially."""
    provider = AsyncMock()
    responses = []
    for c in contents:
        mock_resp = MagicMock()
        mock_resp.content = c
        responses.append(mock_resp)
    provider.chat = AsyncMock(side_effect=responses)
    return provider


SKILL_MD = (
    "---\nname: ci-pipeline\ndescription: CI 流水线\n---\n"
    "## When to use\nCI 场景\n\n## Rules\n- 必须通过测试\n- 禁止直接 push\n"
)

CHANGE_SUMMARY_BLOCK = (
    "---change_summary---\n"
    '{"preserved_points": ["保留了必须通过测试规则", "保留了禁止直接push规则"], '
    '"added_points": ["新增了部署前检查步骤"], '
    '"changed_points": [], '
    '"ignored_points": ["v2中的一次性路径"]}\n'
    "---end_change_summary---"
)

CHANGE_SUMMARY_WITH_CHANGE = (
    "---change_summary---\n"
    '{"preserved_points": ["保留了禁止直接push规则"], '
    '"added_points": ["新增了部署前检查步骤"], '
    '"changed_points": [{"original_zh": "必须通过测试", "new_zh": "必须通过单元测试和集成测试", "reason_zh": "v2经验表明仅单元测试不够"}], '
    '"ignored_points": ["v2中的一次性路径"]}\n'
    "---end_change_summary---"
)

CHANGE_SUMMARY_NO_REASON = (
    "---change_summary---\n"
    '{"preserved_points": ["p1"], '
    '"added_points": ["a1"], '
    '"changed_points": [{"original_zh": "旧规则", "new_zh": "新规则"}], '
    '"ignored_points": []}\n'
    "---end_change_summary---"
)


# ── Tests ─────────────────────────────────────────────────────────────────

class TestConservationLawPrompt:

    def test_merge_generate_prompt_has_conservation_law(self):
        assert "核心守恒原则" in _MERGE_GENERATE_PROMPT
        assert "Conservation Law" in _MERGE_GENERATE_PROMPT

    def test_merge_generate_prompt_forbids_weakening(self):
        assert "不得删除、弱化、重写" in _MERGE_GENERATE_PROMPT

    def test_merge_generate_prompt_requires_change_summary(self):
        assert "change_summary" in _MERGE_GENERATE_PROMPT
        assert "preserved_points" in _MERGE_GENERATE_PROMPT
        assert "added_points" in _MERGE_GENERATE_PROMPT
        assert "changed_points" in _MERGE_GENERATE_PROMPT

    def test_merge_generate_prompt_requires_reason_for_changes(self):
        assert "changed_points" in _MERGE_GENERATE_PROMPT
        assert "reason_zh" in _MERGE_GENERATE_PROMPT

    def test_merge_generate_prompt_forbids_scope_expansion(self):
        assert "不得为了" in _MERGE_GENERATE_PROMPT or "扩大 skill 适用范围" in _MERGE_GENERATE_PROMPT


class TestChangeSummaryExtraction:

    @pytest.mark.asyncio
    async def test_merge_generate_extracts_change_summary(self, tmp_path: Path):
        store = _make_store(tmp_path)
        skill_with_cs = SKILL_MD + "\n" + CHANGE_SUMMARY_BLOCK

        provider = _mock_provider_with_responses(skill_with_cs)
        store.set_provider(provider, model="test")
        req = _make_request(store)

        content, cs = await store._call_llm_merge_generate_async(
            canonical_request=req, merge_brief={}, selected_events=[], other_extra="",
        )

        # Content should have change_summary block stripped
        assert content is not None
        assert "---change_summary---" not in content
        assert "---end_change_summary---" not in content
        assert "## When to use" in content

        # change_summary should be parsed
        assert cs is not None
        assert len(cs["preserved_points"]) == 2
        assert len(cs["added_points"]) == 1
        assert cs["changed_points"] == []

    @pytest.mark.asyncio
    async def test_merge_generate_no_change_summary_returns_none_cs(self, tmp_path: Path):
        """_call_llm_merge_generate_async returns (content, None) when LLM omits change_summary."""
        store = _make_store(tmp_path)
        provider = _mock_provider_with_responses(SKILL_MD)
        store.set_provider(provider, model="test")
        req = _make_request(store)

        content, cs = await store._call_llm_merge_generate_async(
            canonical_request=req, merge_brief={}, selected_events=[], other_extra="",
        )

        assert content is not None
        assert "## When to use" in content
        assert cs is None  # No change_summary = None at extraction level


class TestChangeSummaryValidation:

    @pytest.mark.asyncio
    async def test_change_summary_requires_reason_for_changed_points(self, tmp_path: Path):
        """changed_points without reason_zh should block enhanced pending creation."""
        store = _make_store(tmp_path)

        skill_with_bad_cs = SKILL_MD + "\n" + CHANGE_SUMMARY_NO_REASON
        # Stage 1: brief says yes
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "新规则", "source": "canonical"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json

        # Stage 2: generates with change_summary that has changed_points without reason
        gen_resp = MagicMock()
        gen_resp.content = skill_with_bad_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
            other_extra="",
        )

        assert result["status"] == "error"
        assert "未说明原因" in result["message"] or "reason" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_missing_change_summary_blocks_enhanced(self, tmp_path: Path):
        """LLM omits change_summary entirely → fail-closed, no enhanced pending created."""
        store = _make_store(tmp_path)

        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "新规则", "source": "canonical"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json

        # Stage 2: LLM returns SKILL.md WITHOUT change_summary block
        gen_resp = MagicMock()
        gen_resp.content = SKILL_MD

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
            other_extra="",
        )

        assert result["status"] == "error"
        assert "未输出变更摘要" in result["message"]

    @pytest.mark.asyncio
    async def test_non_dict_change_summary_blocks_enhanced(self, tmp_path: Path):
        """change_summary is a string instead of dict → extraction returns None → fail-closed."""
        store = _make_store(tmp_path)

        bad_cs = (
            "---change_summary---\n"
            '"not a dict"\n'
            "---end_change_summary---"
        )
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "新规则", "source": "canonical"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json
        gen_resp = MagicMock()
        gen_resp.content = SKILL_MD + "\n" + bad_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
        )

        assert result["status"] == "error"
        # Extraction regex \{...\} won't match "not a dict", so change_summary=None
        assert "未输出变更摘要" in result["message"]

    @pytest.mark.asyncio
    async def test_non_list_field_blocks_enhanced(self, tmp_path: Path):
        """preserved_points is a string instead of list → fail-closed."""
        store = _make_store(tmp_path)

        bad_cs = (
            "---change_summary---\n"
            '{"preserved_points": "oops", "added_points": [], "changed_points": [], "ignored_points": []}\n'
            "---end_change_summary---"
        )
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "新规则", "source": "canonical"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json
        gen_resp = MagicMock()
        gen_resp.content = SKILL_MD + "\n" + bad_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
        )

        assert result["status"] == "error"
        assert "preserved_points" in result["message"]

    @pytest.mark.asyncio
    async def test_non_dict_changed_points_entry_blocks_enhanced(self, tmp_path: Path):
        """changed_points entry is a string instead of dict → fail-closed."""
        store = _make_store(tmp_path)

        bad_cs = (
            "---change_summary---\n"
            '{"preserved_points": [], "added_points": [], "changed_points": ["not a dict"], "ignored_points": []}\n'
            "---end_change_summary---"
        )
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "新规则", "source": "canonical"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json
        gen_resp = MagicMock()
        gen_resp.content = SKILL_MD + "\n" + bad_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
        )

        assert result["status"] == "error"
        assert "changed_points" in result["message"]


class TestEnhancedTriggerConversation:

    @pytest.mark.asyncio
    async def test_enhanced_trigger_conversation_includes_change_summary(self, tmp_path: Path):
        """trigger_conversation of enhanced pending includes change_summary_zh."""
        store = _make_store(tmp_path)

        skill_with_cs = SKILL_MD + "\n" + CHANGE_SUMMARY_BLOCK
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "部署前检查", "source": "canonical"}],
            "ignored_points": [{"point_zh": "一次性路径", "reason_zh": "不通用"}],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json

        gen_resp = MagicMock()
        gen_resp.content = skill_with_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
            other_extra="",
        )

        assert result["status"] == "pending_review"

        # Read the enhanced pending's trigger_conversation
        enhanced = store.get_request(result["request_id"])
        tc = enhanced.trigger_conversation

        assert "变更摘要" in tc or "change_summary_zh" in tc
        assert "保留" in tc
        assert "新增" in tc

    @pytest.mark.asyncio
    async def test_enhanced_with_changed_points_includes_reason(self, tmp_path: Path):
        """When changed_points have reasons, trigger_conversation shows them."""
        store = _make_store(tmp_path)

        skill_with_cs = SKILL_MD + "\n" + CHANGE_SUMMARY_WITH_CHANGE
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "集成测试", "source": "dup:1"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json
        gen_resp = MagicMock()
        gen_resp.content = skill_with_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
        )

        assert result["status"] == "pending_review"
        enhanced = store.get_request(result["request_id"])
        tc = enhanced.trigger_conversation
        assert "修改" in tc
        assert "单元测试" in tc


class TestConservationLawBehavior:

    @pytest.mark.asyncio
    async def test_merge_generate_preserves_canonical_rules(self, tmp_path: Path):
        """Enhanced SKILL.md content does not include the change_summary block."""
        store = _make_store(tmp_path)

        skill_with_cs = SKILL_MD + "\n" + CHANGE_SUMMARY_BLOCK
        brief_json = json.dumps({
            "absorbed_points": [{"type": "workflow", "point_zh": "部署前检查", "source": "canonical"}],
            "ignored_points": [],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "值得增强",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json
        gen_resp = MagicMock()
        gen_resp.content = skill_with_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
        )

        assert result["status"] == "pending_review"
        enhanced = store.get_request(result["request_id"])

        # proposed_content should be clean SKILL.md without change_summary markers
        assert "---change_summary---" not in enhanced.proposed_content
        assert "---end_change_summary---" not in enhanced.proposed_content

    @pytest.mark.asyncio
    async def test_generate_enhanced_with_change_summary_success(self, tmp_path: Path):
        """Full pipeline with valid change_summary creates pending with summary in trigger_conversation."""
        store = _make_store(tmp_path)

        skill_with_cs = SKILL_MD + "\n" + CHANGE_SUMMARY_WITH_CHANGE
        brief_json = json.dumps({
            "absorbed_points": [{"type": "rule", "point_zh": "集成测试", "source": "dup:1"}],
            "ignored_points": [{"point_zh": "临时路径", "reason_zh": "不通用"}],
            "conflicts": [],
            "skill_shape": {"name": "ci-pipeline", "description_zh": "CI"},
            "should_generate_enhanced": True,
            "summary_zh": "增强版包含集成测试要求",
        })
        brief_resp = MagicMock()
        brief_resp.content = brief_json
        gen_resp = MagicMock()
        gen_resp.content = skill_with_cs

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=[brief_resp, gen_resp])
        store.set_provider(provider, model="test")

        req = _make_request(store)
        evt_id = _make_event(store, req.id)

        result = await store.generate_enhanced_candidate(
            target_request_id=req.id,
            selected_event_ids=[evt_id],
            other_extra="集成测试经验",
        )

        assert result["status"] == "pending_review"
        assert "request_id" in result

        enhanced = store.get_request(result["request_id"])
        assert enhanced.status == "pending"
        assert enhanced.reason.startswith("[增强版候选]")

        # trigger_conversation includes all key sections
        tc = enhanced.trigger_conversation
        assert "增强版候选生成记录" in tc
        assert "变更摘要" in tc
        assert "保留" in tc
        assert "新增" in tc
        assert "修改" in tc
        assert "集成测试" in tc

        # proposed_content is clean
        assert "---change_summary---" not in enhanced.proposed_content
        assert "## When to use" in enhanced.proposed_content
        assert "## Rules" in enhanced.proposed_content
