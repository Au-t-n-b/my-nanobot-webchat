"""Tests for Round 3C: Duplicate Extra Info + Generate Enhanced Candidate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_change_store import (
    DuplicateEvent,
    SkillChangeRequest,
    SkillChangeStore,
    _redact,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(tmp_path, expiry_days=60, duplicate_grace_days=14)


def _make_request(store: SkillChangeStore, **overrides) -> SkillChangeRequest:
    defaults = {
        "action": "create", "skill_name": "ci-pipeline",
        "reason": "搭建 CI 流水线",
    }
    defaults.update(overrides)
    return store.create_request(**defaults)


def _make_judge_result(**overrides) -> dict:
    defaults = {
        "decision": "same_duplicate",
        "confidence": 0.92,
        "target_id": None,
        "reason_zh": "两个请求语义相同",
    }
    defaults.update(overrides)
    return defaults


# ── Part A: DuplicateEvent data model ────────────────────────────────────

def test_duplicate_event_to_dict():
    ev = DuplicateEvent(
        id="abc", target_request_id="req1", candidate_skill_name="ci",
        candidate_reason="搭建CI", candidate_trigger_conversation="证据",
        candidate_content_excerpt="内容", judge_confidence=0.9,
        judge_reason_zh="相同", created_at="2026-01-01",
    )
    d = ev.to_dict()
    assert d["id"] == "abc"
    assert d["target_request_id"] == "req1"
    assert d["judge_confidence"] == 0.9


# ── Part B: create_duplicate_event ───────────────────────────────────────

def test_create_duplicate_event(store: SkillChangeStore):
    req = _make_request(store)
    event = store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={
            "skill_name": "ci-pipeline",
            "reason": "配置 CI 流水线",
            "trigger_conversation": "用户意图：搭建CI",
            "proposed_content": "---\nname: ci\n---\n内容",
        },
        judge_result=_make_judge_result(confidence=0.88, reason_zh="语义相同"),
    )
    assert event.id
    assert event.target_request_id == req.id
    assert event.candidate_reason == "配置 CI 流水线"
    assert event.judge_confidence == 0.88
    assert event.judge_reason_zh == "语义相同"


def test_create_duplicate_event_truncation(store: SkillChangeStore):
    req = _make_request(store)
    event = store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={
            "skill_name": "ci",
            "reason": "x" * 500,
            "trigger_conversation": "y" * 1000,
            "proposed_content": "z" * 2000,
        },
        judge_result=_make_judge_result(reason_zh="r" * 500),
    )
    assert len(event.candidate_reason) <= 300
    assert len(event.candidate_trigger_conversation) <= 500
    assert len(event.candidate_content_excerpt) <= 500
    assert len(event.judge_reason_zh) <= 300


def test_create_duplicate_event_redacts_secrets(store: SkillChangeStore):
    req = _make_request(store)
    event = store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={
            "skill_name": "ci",
            "reason": "API_KEY=sk-abc123 配置认证",
            "trigger_conversation": "",
            "proposed_content": "Authorization: Bearer token_xyz",
        },
        judge_result=_make_judge_result(),
    )
    assert "sk-abc123" not in event.candidate_reason
    assert "token_xyz" not in event.candidate_content_excerpt


# ── Part C: list_duplicate_events ────────────────────────────────────────

def test_list_duplicate_events_ordering(store: SkillChangeStore):
    req = _make_request(store)
    store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={"skill_name": "ci", "reason": "first", "trigger_conversation": "", "proposed_content": ""},
        judge_result=_make_judge_result(),
    )
    store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={"skill_name": "ci", "reason": "second", "trigger_conversation": "", "proposed_content": ""},
        judge_result=_make_judge_result(),
    )
    events = store.list_duplicate_events(req.id)
    assert len(events) == 2
    # DESC by created_at
    assert events[0].candidate_reason == "second"
    assert events[1].candidate_reason == "first"


def test_list_duplicate_events_limit(store: SkillChangeStore):
    req = _make_request(store)
    for i in range(5):
        store.create_duplicate_event(
            target_request_id=req.id,
            candidate_data={"skill_name": "ci", "reason": f"r{i}", "trigger_conversation": "", "proposed_content": ""},
            judge_result=_make_judge_result(),
        )
    events = store.list_duplicate_events(req.id, limit=3)
    assert len(events) == 3


def test_list_duplicate_events_isolated(store: SkillChangeStore):
    req1 = _make_request(store, skill_name="a")
    req2 = _make_request(store, skill_name="b")
    store.create_duplicate_event(
        target_request_id=req1.id,
        candidate_data={"skill_name": "a", "reason": "for a", "trigger_conversation": "", "proposed_content": ""},
        judge_result=_make_judge_result(),
    )
    events_b = store.list_duplicate_events(req2.id)
    assert len(events_b) == 0


# ── Part D: get_duplicate_events_by_ids ──────────────────────────────────

def test_get_duplicate_events_by_ids_valid(store: SkillChangeStore):
    req = _make_request(store)
    e1 = store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={"skill_name": "ci", "reason": "r1", "trigger_conversation": "", "proposed_content": ""},
        judge_result=_make_judge_result(),
    )
    e2 = store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={"skill_name": "ci", "reason": "r2", "trigger_conversation": "", "proposed_content": ""},
        judge_result=_make_judge_result(),
    )
    found = store.get_duplicate_events_by_ids(req.id, [e1.id, e2.id])
    assert len(found) == 2


def test_get_duplicate_events_by_ids_wrong_target(store: SkillChangeStore):
    req1 = _make_request(store, skill_name="a")
    req2 = _make_request(store, skill_name="b")
    e1 = store.create_duplicate_event(
        target_request_id=req1.id,
        candidate_data={"skill_name": "a", "reason": "r1", "trigger_conversation": "", "proposed_content": ""},
        judge_result=_make_judge_result(),
    )
    # Looking for req1's events under req2's target → should return empty
    found = store.get_duplicate_events_by_ids(req2.id, [e1.id])
    assert len(found) == 0


def test_get_duplicate_events_by_ids_empty(store: SkillChangeStore):
    found = store.get_duplicate_events_by_ids("nonexistent", [])
    assert len(found) == 0


# ── Part E: _merge_into_existing creates events ──────────────────────────

def test_merge_into_existing_creates_event(store: SkillChangeStore):
    req1 = _make_request(store)
    judge = _make_judge_result(target_id=req1.id, confidence=0.92)
    req2 = store.create_request(
        action="create", skill_name="ci-pipeline",
        reason="配置 CI 流水线", judge_result=judge,
    )
    assert req2.status == "merged_with_existing"
    events = store.list_duplicate_events(req1.id)
    assert len(events) == 1
    assert events[0].candidate_reason == "配置 CI 流水线"


def test_merge_into_existing_event_failure_tolerated(store: SkillChangeStore):
    req1 = _make_request(store)
    judge = _make_judge_result(target_id=req1.id, confidence=0.92)
    # This will trigger merge. Event creation should succeed.
    req2 = store.create_request(
        action="create", skill_name="ci-pipeline",
        reason="另一个 CI 请求", judge_result=judge,
    )
    # Merge should have succeeded even if event had issues
    assert req2.status == "merged_with_existing"
    assert store.pending_count() == 1


def test_duplicate_event_does_not_create_top_level_pending(store: SkillChangeStore):
    req1 = _make_request(store)
    judge = _make_judge_result(target_id=req1.id, confidence=0.92)
    store.create_request(
        action="create", skill_name="ci-pipeline",
        reason="重复请求", judge_result=judge,
    )
    # Should still be 1 pending (the original), not 2
    assert store.pending_count() == 1


# ── Part F: LLM merge_brief parsing ─────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_brief_parse_success(store: SkillChangeStore):
    req = _make_request(store)
    events = [
        DuplicateEvent(
            id="ev1", target_request_id=req.id, candidate_skill_name="ci",
            candidate_reason="CI", candidate_trigger_conversation="",
            candidate_content_excerpt="", judge_confidence=0.9,
            judge_reason_zh="same", created_at="2026-01-01",
        ),
    ]
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "规则", "source": "canonical"}],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "CI", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "值得生成",
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=events, other_extra="",
    )
    assert result is not None
    assert result["should_generate_enhanced"] is True


@pytest.mark.asyncio
async def test_merge_brief_thinking_tag_handling(store: SkillChangeStore):
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = '<think\nthinking here\n</think\n\n' + json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": False, "summary_zh": "无新增",
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is not None
    assert result["should_generate_enhanced"] is False


@pytest.mark.asyncio
async def test_merge_brief_invalid_json_returns_none(store: SkillChangeStore):
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "This is not JSON"
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is None


@pytest.mark.asyncio
async def test_merge_brief_missing_required_keys_returns_none(store: SkillChangeStore):
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({"absorbed_points": []})  # missing keys
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is None


@pytest.mark.asyncio
async def test_merge_brief_no_provider_returns_none(store: SkillChangeStore):
    req = _make_request(store)
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is None


# ── Part G: LLM merge_generate ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_generate_valid_frontmatter(store: SkillChangeStore):
    req = _make_request(store)
    skill_md = "---\nname: ci-pipeline\ndescription: CI 流水线\n---\n## When to use\nCI场景"
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = skill_md
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    brief = {
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True,
    }
    result = await store._call_llm_merge_generate_async(
        canonical_request=req, merge_brief=brief, selected_events=[], other_extra="",
    )
    assert result == skill_md


@pytest.mark.asyncio
async def test_merge_generate_no_frontmatter_returns_none(store: SkillChangeStore):
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "Just some text without frontmatter"
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_generate_async(
        canonical_request=req, merge_brief={}, selected_events=[], other_extra="",
    )
    assert result is None


# ── Part H: generate_enhanced_candidate orchestrator ─────────────────────

@pytest.mark.asyncio
async def test_generate_enhanced_candidate_full(store: SkillChangeStore):
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    # Create duplicate events
    e1 = store.create_duplicate_event(
        target_request_id=req.id,
        candidate_data={"skill_name": "ci", "reason": "CI 配置", "trigger_conversation": "证据", "proposed_content": "内容"},
        judge_result=_make_judge_result(),
    )
    # Mock LLM
    mock_provider = AsyncMock()
    # Stage 1: brief
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "规则", "source": "dup:" + e1.id}],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "增强版CI", "use_when": ["CI"], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "吸收了额外规则",
    })
    # Stage 2: generate
    gen_response = MagicMock()
    gen_response.content = "---\nname: ci-pipeline\ndescription: 增强版CI\n---\n## When to use\nCI\n## Rules\n规则"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id,
        selected_event_ids=[e1.id],
        other_extra="",
    )
    assert result["status"] == "pending_review"
    assert result["request_id"]
    # Original pending unchanged
    assert store.pending_count() == 2
    # New request has enhanced content
    new_req = store.get_request(result["request_id"])
    assert new_req is not None
    assert "[增强版候选]" in new_req.reason


@pytest.mark.asyncio
async def test_generate_enhanced_candidate_brief_says_no(store: SkillChangeStore):
    req = _make_request(store)
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [{"point_zh": "无价值", "reason_zh": "重复"}],
        "conflicts": [],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": False,
        "summary_zh": "无新增信息",
    })
    mock_provider.chat = AsyncMock(return_value=brief_response)
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="无",
    )
    assert result["status"] == "needs_human_resolution"


@pytest.mark.asyncio
async def test_generate_enhanced_candidate_no_provider(store: SkillChangeStore):
    req = _make_request(store)
    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="test",
    )
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_generate_enhanced_candidate_not_pending(store: SkillChangeStore):
    req = _make_request(store)
    store.approve_request(req.id)
    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="test",
    )
    assert result["status"] == "error"
    assert "not pending" in result["message"]


@pytest.mark.asyncio
async def test_generate_enhanced_candidate_validation_failure(store: SkillChangeStore):
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True, "summary_zh": "ok",
    })
    gen_response = MagicMock()
    gen_response.content = "Not valid SKILL.md"  # no frontmatter
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="补充",
    )
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_original_pending_remains_unchanged(store: SkillChangeStore):
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n原始内容")
    original_reason = req.reason
    original_content = req.proposed_content

    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True, "summary_zh": "ok",
    })
    gen_response = MagicMock()
    gen_response.content = "---\nname: ci-pipeline\ndescription: enhanced\n---\n增强内容"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="补充",
    )
    # Original unchanged
    original = store.get_request(req.id)
    assert original.reason == original_reason
    assert original.proposed_content == original_content
    assert original.status == "pending"


# ── Part I: Security audit tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_brief_rejects_unknown_source(store: SkillChangeStore):
    """absorbed_points with invalid source should cause brief to return None."""
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "规则", "source": "untrusted_source"}],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "CI", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "ok",
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is None


@pytest.mark.asyncio
async def test_merge_brief_rejects_non_dict_absorbed_point(store: SkillChangeStore):
    """absorbed_points entry that is not a dict should cause brief to return None."""
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "absorbed_points": ["not_a_dict"],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "ci", "description_zh": "", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "ok",
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is None


@pytest.mark.asyncio
async def test_merge_brief_rejects_missing_keys_in_point(store: SkillChangeStore):
    """absorbed_points entry missing 'source' key should cause brief to return None."""
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "规则"}],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "ci", "description_zh": "", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "ok",
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is None


@pytest.mark.asyncio
async def test_merge_brief_accepts_valid_dup_source(store: SkillChangeStore):
    """absorbed_points with source 'dup:<event_id>' should pass validation."""
    req = _make_request(store)
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "规则", "source": "dup:ev123"}],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "CI", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "ok",
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test")
    result = await store._call_llm_merge_brief_async(
        canonical_request=req, selected_events=[], other_extra="",
    )
    assert result is not None
    assert result["absorbed_points"][0]["source"] == "dup:ev123"


@pytest.mark.asyncio
async def test_enhanced_skill_secret_scan_blocks(store: SkillChangeStore):
    """Generated SKILL.md containing secrets should be blocked."""
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True, "summary_zh": "ok",
    })
    gen_response = MagicMock()
    gen_response.content = "---\nname: ci-pipeline\ndescription: CI with auth\n---\n## When to use\nCI\n## Rules\nAPI_KEY=sk-abc123"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="",
    )
    assert result["status"] == "error"
    assert "sensitive" in result["message"].lower()


@pytest.mark.asyncio
async def test_enhanced_skill_name_mismatch_blocked(store: SkillChangeStore):
    """Generated SKILL.md with wrong name field should be blocked."""
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True, "summary_zh": "ok",
    })
    gen_response = MagicMock()
    gen_response.content = "---\nname: wrong-name\ndescription: CI\n---\n## When to use\nCI\n## Rules\n规则"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="",
    )
    assert result["status"] == "error"
    assert "does not match" in result["message"]


@pytest.mark.asyncio
async def test_enhanced_skill_missing_required_section(store: SkillChangeStore):
    """Generated SKILL.md missing 'Rules' section should be blocked."""
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True, "summary_zh": "ok",
    })
    gen_response = MagicMock()
    gen_response.content = "---\nname: ci-pipeline\ndescription: CI\n---\n## When to use\nCI场景"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="",
    )
    assert result["status"] == "error"
    assert "missing required section" in result["message"]


@pytest.mark.asyncio
async def test_enhanced_skill_empty_description_blocked(store: SkillChangeStore):
    """Generated SKILL.md with empty description should be blocked."""
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [], "ignored_points": [], "conflicts": [],
        "skill_shape": {"name": "ci-pipeline"}, "should_generate_enhanced": True, "summary_zh": "ok",
    })
    gen_response = MagicMock()
    gen_response.content = "---\nname: ci-pipeline\ndescription:\n---\n## When to use\nCI\n## Rules\n规则"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="",
    )
    assert result["status"] == "error"
    assert "empty description" in result["message"].lower()


@pytest.mark.asyncio
async def test_trigger_conversation_includes_absorbed_details(store: SkillChangeStore):
    """trigger_conversation of enhanced request should include actual absorbed point content."""
    req = _make_request(store, proposed_content="---\nname: ci-pipeline\ndescription: CI\n---\n内容")
    mock_provider = AsyncMock()
    brief_response = MagicMock()
    brief_response.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "使用缓存加速", "source": "dup:ev1"}],
        "ignored_points": [{"point_zh": "过时建议", "reason_zh": "已废弃"}],
        "conflicts": [{"topic_zh": "部署策略", "canonical_zh": "蓝绿部署", "extra_zh": "金丝雀发布", "resolution_zh": "保留两种"}],
        "skill_shape": {"name": "ci-pipeline", "description_zh": "增强CI", "use_when": [], "do_not_use_when": []},
        "should_generate_enhanced": True,
        "summary_zh": "吸收了缓存规则",
    })
    gen_response = MagicMock()
    gen_response.content = "---\nname: ci-pipeline\ndescription: 增强CI\n---\n## When to use\nCI\n## Rules\n使用缓存加速"
    mock_provider.chat = AsyncMock(side_effect=[brief_response, gen_response])
    store.set_provider(mock_provider, model="test")

    result = await store.generate_enhanced_candidate(
        target_request_id=req.id, selected_event_ids=[], other_extra="",
    )
    assert result["status"] == "pending_review"
    new_req = store.get_request(result["request_id"])
    tc = new_req.trigger_conversation
    # Should contain actual content, not just counts
    assert "使用缓存加速" in tc
    assert "dup:ev1" in tc
    assert "过时建议" in tc
    assert "已废弃" in tc
    assert "部署策略" in tc
    assert "蓝绿部署" in tc
    assert "金丝雀发布" in tc
