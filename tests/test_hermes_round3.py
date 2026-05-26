"""Tests for Round 3A+ adjustment: LLM semantic judge, prefilter-only n-gram."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_change_store import (
    BlacklistEntry,
    SkillChangeRequest,
    SkillChangeStore,
    build_similarity_key,
    char_ngrams,
    normalize_text_for_similarity,
    similarity_score,
    _redact,
)
from nanobot.config.schema import SkillsAutoConfig


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(tmp_path, expiry_days=60, duplicate_grace_days=14)


def _make_config(**overrides) -> SkillsAutoConfig:
    defaults = {
        "hermes_enabled": True,
        "hermes_nudge_interval": 10,
        "hermes_cooldown_turns": 5,
        "hermes_max_pending": 5,
        "hermes_max_reviews_per_session": 3,
    }
    defaults.update(overrides)
    return SkillsAutoConfig(**defaults)


# ── Part A: Evidence summary (unchanged from prior round) ────────────────

def _import_evidence_summary():
    from nanobot.agent.loop import AgentLoop
    return AgentLoop._build_review_evidence_summary


def test_evidence_summary_includes_user_intent():
    summary_fn = _import_evidence_summary()
    messages = [
        {"role": "user", "content": "帮我搭建一个 CI pipeline 用于 Python 项目"},
        {"role": "assistant", "content": "我来帮你配置 CI。"},
        {"role": "assistant", "content": f"[Tool summary: exec]\n{json.dumps({'tool': 'exec', 'head': 'ok', 'tail': 'done', 'errors': None, 'test_results': None, 'file_paths': None, 'truncated': False, 'original_chars': 100}, ensure_ascii=False)}"},
    ]
    result = summary_fn(messages)
    assert "【用户意图】" in result
    assert "CI" in result


def test_evidence_summary_includes_user_corrections():
    summary_fn = _import_evidence_summary()
    messages = [
        {"role": "user", "content": "配置 CI"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "以后记得用 GitHub Actions，不要用 Jenkins"},
    ]
    result = summary_fn(messages)
    assert "【用户偏好/纠正】" in result


def test_evidence_summary_includes_tool_errors_and_tests():
    summary_fn = _import_evidence_summary()
    tool_summary = json.dumps({
        "tool": "exec", "head": "running...", "tail": "done",
        "errors": "AssertionError: expected 200 got 500",
        "test_results": "48 passed, 2 failed",
        "file_paths": ["src/test.py"], "truncated": True, "original_chars": 5000,
    }, ensure_ascii=False)
    messages = [
        {"role": "user", "content": "run tests"},
        {"role": "assistant", "content": f"[Tool summary: exec]\n{tool_summary}"},
    ]
    result = summary_fn(messages)
    assert "【关键工具行为】" in result


def test_evidence_summary_redacts_secrets():
    summary_fn = _import_evidence_summary()
    messages = [{"role": "user", "content": "使用这个 API_KEY=sk-abc123 配置认证"}]
    result = summary_fn(messages)
    assert "sk-abc123" not in result
    assert "***" in result


def test_evidence_summary_has_size_limit():
    summary_fn = _import_evidence_summary()
    messages = [{"role": "user", "content": "x" * 10000}]
    result = summary_fn(messages)
    assert len(result) <= 8000


def test_evidence_summary_includes_trigger_context():
    summary_fn = _import_evidence_summary()
    messages = [{"role": "user", "content": "test"}]
    hs = {"iters_since_skill_manage": 15, "user_turns_since_review": 8, "reviews_this_session": 2}
    result = summary_fn(messages, hermes_state=hs, pending_count=3)
    assert "【触发原因】" in result


# ── Part B: trigger_conversation stored ───────────────────────────────────

def test_skill_manage_stores_trigger_conversation(store: SkillChangeStore):
    req = store.create_request(
        action="create", skill_name="my-skill", reason="good reason",
        trigger_conversation="【用户意图】\n- 搭建 CI pipeline",
    )
    assert req.trigger_conversation == "【用户意图】\n- 搭建 CI pipeline"
    fetched = store.get_request(req.id)
    assert fetched is not None
    assert "CI pipeline" in fetched.trigger_conversation


def test_skill_manage_trigger_conversation_defaults_empty(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="no-evidence", reason="r")
    assert req.trigger_conversation == ""


# ── Part C: N-gram similarity is prefilter only ──────────────────────────

def test_ngram_similarity_only_prefilters_not_merges(store: SkillChangeStore):
    """Without judge_result, n-gram similarity should NOT auto-merge."""
    store.create_request(action="create", skill_name="ci-pipeline", reason="搭建 CI 流水线")
    req2 = store.create_request(action="create", skill_name="ci-pipeline", reason="CI 流水线配置")
    # No judge_result → always creates new pending
    assert req2.status == "pending"
    assert store.pending_count() == 2


def test_normalize_text_removes_punctuation():
    result = normalize_text_for_similarity("Hello, World！测试。")
    assert "," not in result


def test_char_ngrams_basic():
    ngrams = char_ngrams("abcde", n=3)
    assert "abc" in ngrams and "cde" in ngrams


def test_char_ngrams_chinese():
    ngrams = char_ngrams("中文测试", n=3)
    assert len(ngrams) > 0


def test_similarity_identical_strings():
    assert similarity_score("本地 agent bearer token 认证", "本地 agent bearer token 认证") == 1.0


def test_similarity_different_strings():
    assert similarity_score("completely different topic", "totally unrelated subject") < 0.5


def test_chinese_similarity_detects_equivalent():
    score = similarity_score("本地 agent bearer token 认证", "本地代理 bearer token 鉴权")
    assert score > 0.3


def test_build_similarity_key_deterministic():
    key1 = build_similarity_key("create", "my-skill", "因为XXX原因")
    key2 = build_similarity_key("create", "my-skill", "因为XXX原因")
    assert key1 == key2


# ── Part D: LLM judge-driven merge ──────────────────────────────────────

def test_llm_judge_same_duplicate_merges_pending(store: SkillChangeStore):
    """When judge says same_duplicate with high confidence, merge happens."""
    req1 = store.create_request(action="create", skill_name="ci-setup", reason="CI 流水线")
    judge = {
        "decision": "same_duplicate",
        "confidence": 0.92,
        "target_id": req1.id,
        "reason_zh": "两个请求都是关于 CI 流水线搭建",
        "should_merge": True,
        "should_increment_duplicate_count": True,
        "should_refresh_expiry": True,
        "should_raise_priority": True,
    }
    req2 = store.create_request(
        action="create", skill_name="ci-setup", reason="CI 配置", judge_result=judge,
    )
    assert req2.status == "merged_with_existing"
    assert req2.duplicate_count == 1
    assert store.pending_count() == 1


def test_llm_judge_related_but_distinct_does_not_merge(store: SkillChangeStore):
    """When judge says related_but_distinct, create new pending with maybe_duplicate_ids."""
    req1 = store.create_request(action="create", skill_name="deploy-k8s", reason="K8s 部署")
    judge = {
        "decision": "related_but_distinct",
        "confidence": 0.85,
        "target_id": req1.id,
        "reason_zh": "一个是部署，一个是监控，相关但不相同",
        "should_merge": False,
        "should_increment_duplicate_count": False,
        "should_refresh_expiry": False,
        "should_raise_priority": False,
    }
    req2 = store.create_request(
        action="create", skill_name="monitor-k8s", reason="K8s 监控配置", judge_result=judge,
    )
    assert req2.status == "pending"
    assert req2.id != req1.id
    assert store.pending_count() == 2
    assert req2.maybe_duplicate_ids is not None
    assert req1.id in req2.maybe_duplicate_ids


def test_llm_judge_low_confidence_does_not_merge(store: SkillChangeStore):
    """When judge says same_duplicate but confidence < 0.80, don't merge."""
    req1 = store.create_request(action="create", skill_name="test-skill", reason="r1")
    judge = {
        "decision": "same_duplicate",
        "confidence": 0.65,
        "target_id": req1.id,
        "reason_zh": "可能相似但不确定",
        "should_merge": False,
    }
    req2 = store.create_request(
        action="create", skill_name="test-skill", reason="r2", judge_result=judge,
    )
    # Low confidence → falls through to "related_but_distinct" path
    assert req2.status == "pending"
    assert req2.id != req1.id


def test_llm_judge_blacklist_hit_blocks_request(store: SkillChangeStore):
    """When judge says blacklist_hit with confidence >= 0.85, block."""
    # Setup: create and reject, add to blacklist
    req = store.create_request(action="create", skill_name="bad-skill", reason="r")
    store.reject_request(req.id)
    store.create_blacklist_from_request(req, note="Not useful")

    judge = {
        "decision": "blacklist_hit",
        "confidence": 0.92,
        "target_id": None,
        "reason_zh": "命中用户黑名单模式",
        "should_merge": False,
    }
    req2 = store.create_request(
        action="create", skill_name="bad-skill", reason="similar", judge_result=judge,
    )
    assert req2.status == "blocked_by_blacklist"
    assert req2.id == "blacklisted"


def test_llm_judge_blacklist_low_confidence_does_not_block(store: SkillChangeStore):
    """When judge says blacklist_hit but confidence < 0.85, create pending with warning."""
    req = store.create_request(action="create", skill_name="suspect", reason="r")
    store.reject_request(req.id)
    store.create_blacklist_from_request(req)

    judge = {
        "decision": "blacklist_hit",
        "confidence": 0.70,
        "target_id": None,
        "reason_zh": "可能命中黑名单",
        "should_merge": False,
    }
    req2 = store.create_request(
        action="create", skill_name="suspect", reason="similar", judge_result=judge,
    )
    # Low confidence blacklist → create pending with suspected_blacklist note
    assert req2.status == "pending"
    assert req2.id != "blacklisted"


def test_llm_judge_failure_falls_back_to_create_pending(store: SkillChangeStore):
    """When no judge_result (LLM failed), create normal pending."""
    store.create_request(action="create", skill_name="x", reason="r1")
    # No judge_result → always creates new pending
    req2 = store.create_request(action="create", skill_name="x", reason="r2")
    assert req2.status == "pending"
    assert store.pending_count() == 2


def test_no_candidates_skips_judge(store: SkillChangeStore):
    """When there are no n-gram candidates at all, no judge needed."""
    req = store.create_request(action="create", skill_name="unique-skill", reason="totally unique")
    assert req.status == "pending"
    assert store.pending_count() == 1


# ── Part D: Async prefilter_and_judge ────────────────────────────────────

@pytest.mark.asyncio
async def test_prefilter_and_judge_returns_none_when_no_candidates(tmp_path: Path):
    store = SkillChangeStore(tmp_path, expiry_days=60)
    result = await store.prefilter_and_judge(
        action="create", skill_name="brand-new", reason="unique",
    )
    assert result == (None, None)


@pytest.mark.asyncio
async def test_prefilter_and_judge_returns_none_when_no_provider(tmp_path: Path):
    store = SkillChangeStore(tmp_path, expiry_days=60)
    store.create_request(action="create", skill_name="x", reason="r")
    # No provider set → returns (None, None)
    result = await store.prefilter_and_judge(
        action="create", skill_name="x", reason="r",
    )
    assert result == (None, None)


@pytest.mark.asyncio
async def test_prefilter_and_judge_calls_llm(tmp_path: Path):
    """Verify prefilter_and_judge collects candidates and calls provider."""
    store = SkillChangeStore(tmp_path, expiry_days=60)
    store.create_request(action="create", skill_name="ci-setup", reason="CI 流水线")

    # Mock provider
    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "decision": "same_duplicate",
        "confidence": 0.90,
        "target_id": store.list_requests(status="pending")[0].id,
        "reason_zh": "相同",
        "should_merge": True,
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test-model")

    result = await store.prefilter_and_judge(
        action="create", skill_name="ci-setup", reason="CI 配置",
    )
    judge_result, coverage_result = result
    assert judge_result is not None
    assert judge_result["decision"] == "same_duplicate"
    mock_provider.chat.assert_called_once()


@pytest.mark.asyncio
async def test_chinese_semantic_duplicate_detected_by_llm_even_with_low_ngram_overlap(tmp_path: Path):
    """LLM can detect semantic duplicates even when n-gram overlap is low."""
    store = SkillChangeStore(tmp_path, expiry_days=60)
    store.create_request(
        action="create", skill_name="local-auth",
        reason="本地 agent bearer token 认证流程",
    )

    mock_provider = AsyncMock()
    # Simulate LLM detecting semantic equivalence despite different words
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "decision": "same_duplicate",
        "confidence": 0.88,
        "target_id": store.list_requests(status="pending")[0].id,
        "reason_zh": "认证和鉴权是同一任务的不同说法",
        "should_merge": True,
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test-model")

    result = await store.prefilter_and_judge(
        action="create", skill_name="local-auth",
        reason="本地代理鉴权机制",
    )
    judge_result, coverage_result = result
    assert judge_result is not None
    assert judge_result["decision"] == "same_duplicate"


@pytest.mark.asyncio
async def test_chinese_related_but_distinct_not_overmerged(tmp_path: Path):
    """LLM correctly distinguishes related-but-distinct requests."""
    store = SkillChangeStore(tmp_path, expiry_days=60)
    store.create_request(
        action="create", skill_name="prod-infra",
        reason="生产环境 K8s 集群部署配置流程",
    )

    mock_provider = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "decision": "related_but_distinct",
        "confidence": 0.82,
        "target_id": store.list_requests(status="pending")[0].id,
        "reason_zh": "部署和监控是不同的任务",
        "should_merge": False,
    })
    mock_provider.chat = AsyncMock(return_value=mock_response)
    store.set_provider(mock_provider, model="test-model")

    # Same skill_name ensures prefilter passes (exact action+name match);
    # LLM judge then distinguishes the different reasons
    result = await store.prefilter_and_judge(
        action="create", skill_name="prod-infra",
        reason="生产环境 K8s 集群监控配置流程",
    )
    judge_result, coverage_result = result
    assert judge_result is not None
    assert judge_result["decision"] == "related_but_distinct"

    # Apply the judge result: should create new pending, not merge
    req2 = store.create_request(
        action="create", skill_name="prod-infra",
        reason="生产环境 K8s 集群监控配置流程",
        judge_result=judge_result,
    )
    assert req2.status == "pending"
    assert store.pending_count() == 2


# ── Part E: Blacklist CRUD ───────────────────────────────────────────────

def test_reject_with_blacklist_creates_blacklist_entry(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="bad-skill", reason="r1")
    store.reject_request(req.id, note="Too specific")
    entry = store.create_blacklist_from_request(req, note="Too specific")
    assert entry.skill_name == "bad-skill"
    assert entry.enabled == 1


def test_disabled_blacklist_entry(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="x", reason="r")
    store.reject_request(req.id)
    entry = store.create_blacklist_from_request(req)
    store.disable_blacklist_entry(entry.id)
    enabled = store.list_blacklist_entries(enabled_only=True)
    assert len(enabled) == 0


def test_blacklist_api_lists_entries(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="y", reason="r")
    store.reject_request(req.id)
    store.create_blacklist_from_request(req, note="Bad")
    entries = store.list_blacklist_entries()
    assert len(entries) == 1


# ── Config ───────────────────────────────────────────────────────────────

def test_config_duplicate_grace_days_default():
    cfg = SkillsAutoConfig()
    assert cfg.hermes_duplicate_grace_days == 14


# ── to_dict includes new fields ──────────────────────────────────────────

def test_request_to_dict_includes_new_fields(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="dict-test", reason="r")
    d = req.to_dict()
    assert "duplicate_count" in d
    assert "last_matched_at" in d
    assert "similarity_key" in d
    assert "trigger_conversation" in d
    assert "maybe_duplicate_ids" in d


def test_blacklist_entry_to_dict():
    entry = BlacklistEntry(
        id="test", skill_name="x", similarity_key="key",
        reason="r", enabled=1, created_at="2026-01-01",
    )
    d = entry.to_dict()
    assert d["id"] == "test"
    assert d["enabled"] == 1


# ── Redaction ────────────────────────────────────────────────────────────

def test_redact_masks_secrets():
    assert "sk-abc123" not in _redact("API_KEY=sk-abc123")
    assert "***" in _redact("Authorization: Bearer token_xyz")
