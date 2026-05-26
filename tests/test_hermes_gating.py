"""Tests for Hermes trigger gating and SkillChangeStore."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.skill_change_store import SkillChangeStore, SkillChangeRequest
from nanobot.config.schema import SkillsAutoConfig


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(tmp_path, expiry_days=60)


# ── SkillChangeStore: basic CRUD ──────────────────────────────────────────

def test_create_request(store: SkillChangeStore):
    req = store.create_request(
        action="create",
        skill_name="test-skill",
        reason="A good reason",
    )
    assert req.id
    assert req.action == "create"
    assert req.skill_name == "test-skill"
    assert req.status == "pending"
    assert req.priority == 0


def test_get_request(store: SkillChangeStore):
    created = store.create_request(action="create", skill_name="x", reason="r")
    fetched = store.get_request(created.id)
    assert fetched is not None
    assert fetched.skill_name == "x"


def test_get_request_not_found(store: SkillChangeStore):
    assert store.get_request("nonexistent") is None


def test_list_requests_filters_by_status(store: SkillChangeStore):
    store.create_request(action="create", skill_name="a", reason="r")
    store.create_request(action="create", skill_name="b", reason="r")
    pending = store.list_requests(status="pending")
    assert len(pending) == 2
    approved = store.list_requests(status="approved")
    assert len(approved) == 0


def test_approve_request(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="x", reason="r")
    result = store.approve_request(req.id)
    assert result is not None
    assert result.status == "approved"
    assert result.reviewed_at is not None


def test_approve_nonexistent(store: SkillChangeStore):
    result = store.approve_request("nonexistent")
    assert result is None


def test_reject_request_saves_note(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="x", reason="r")
    result = store.reject_request(req.id, note="Too specific")
    assert result is not None
    assert result.status == "rejected"
    assert result.reviewer_note == "Too specific"
    assert result.reviewed_at is not None


def test_reject_without_note(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="x", reason="r")
    result = store.reject_request(req.id)
    assert result is not None
    assert result.reviewer_note == ""


def test_rejected_requests_persist(store: SkillChangeStore):
    store.create_request(action="create", skill_name="a", reason="r")
    req2 = store.create_request(action="create", skill_name="b", reason="r")
    store.reject_request(req2.id, note="Duplicate")
    rejected = store.list_requests(status="rejected")
    assert len(rejected) == 1
    assert rejected[0].skill_name == "b"
    assert rejected[0].reviewer_note == "Duplicate"


def test_pending_count(store: SkillChangeStore):
    assert store.pending_count() == 0
    store.create_request(action="create", skill_name="a", reason="r")
    assert store.pending_count() == 1
    store.create_request(action="create", skill_name="b", reason="r")
    assert store.pending_count() == 2
    req = store.list_requests(status="pending")[0]
    store.approve_request(req.id)
    assert store.pending_count() == 1


# ── SkillChangeStore: conflict detection ──────────────────────────────────

def test_conflict_same_name_same_action(store: SkillChangeStore):
    store.create_request(action="create", skill_name="x", reason="r1")
    req2 = store.create_request(action="create", skill_name="x", reason="r2")
    # Without judge_result, n-gram is only a prefilter — no auto-merge
    # Both are created as separate pending requests
    assert req2.status == "pending"
    assert store.pending_count() == 2
    # Both get elevated priority via conflict scan
    fetched = store.get_request(req2.id)
    assert fetched is not None
    assert fetched.priority >= 1


def test_conflict_edit_vs_delete(store: SkillChangeStore):
    store.create_request(action="edit", skill_name="x", reason="r1")
    req2 = store.create_request(action="delete", skill_name="x", reason="r2")
    fetched = store.get_request(req2.id)
    assert fetched is not None
    assert fetched.conflict_ids is not None
    ids = json.loads(fetched.conflict_ids)
    assert len(ids) > 0


def test_no_conflict_different_names(store: SkillChangeStore):
    store.create_request(action="create", skill_name="a", reason="r1")
    req2 = store.create_request(action="create", skill_name="b", reason="r2")
    fetched = store.get_request(req2.id)
    assert fetched.priority == 0
    assert fetched.conflict_ids is None


# ── SkillChangeStore: expiry ─────────────────────────────────────────────

def test_expire_requests(store: SkillChangeStore):
    req = store.create_request(action="create", skill_name="x", reason="r")
    # Manually set expires_at to the past
    import sqlite3
    with store._conn() as conn:
        conn.execute(
            "UPDATE skill_change_requests SET expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", req.id),
        )
    count = store.expire_requests()
    assert count == 1
    assert store.pending_count() == 0
    expired = store.list_requests(status="expired")
    assert len(expired) == 1


# ── Hermes trigger gating logic (unit-level) ─────────────────────────────

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


def test_hermes_config_defaults():
    cfg = SkillsAutoConfig()
    assert cfg.hermes_cooldown_turns == 5
    assert cfg.hermes_max_pending == 5
    assert cfg.hermes_max_reviews_per_session == 3


def test_hermes_config_custom():
    cfg = _make_config(hermes_max_pending=10, hermes_cooldown_turns=3)
    assert cfg.hermes_max_pending == 10
    assert cfg.hermes_cooldown_turns == 3


def test_gating_skips_when_pending_limit_reached(store: SkillChangeStore):
    """Verify pending_count check would block trigger."""
    cfg = _make_config(hermes_max_pending=2)
    store.create_request(action="create", skill_name="a", reason="r")
    store.create_request(action="create", skill_name="b", reason="r")
    assert store.pending_count() >= cfg.hermes_max_pending


def test_gating_skips_when_max_reviews_reached():
    """Verify reviews_this_session check would block trigger."""
    cfg = _make_config(hermes_max_reviews_per_session=3)
    # Simulate session state after 3 reviews
    hs = {
        "iters_since_skill_manage": 15,
        "user_turns_since_review": 10,
        "reviews_this_session": 3,
    }
    should_trigger = (
        hs["iters_since_skill_manage"] >= cfg.hermes_nudge_interval
        and hs["user_turns_since_review"] >= cfg.hermes_cooldown_turns
        and hs["reviews_this_session"] < cfg.hermes_max_reviews_per_session
    )
    assert should_trigger is False


def test_gating_skips_when_cooldown_not_met():
    """Verify cooldown turns check would block trigger."""
    cfg = _make_config(hermes_cooldown_turns=5, hermes_nudge_interval=10)
    hs = {
        "iters_since_skill_manage": 15,
        "user_turns_since_review": 3,  # less than cooldown_turns=5
        "reviews_this_session": 0,
    }
    should_trigger = (
        hs["iters_since_skill_manage"] >= cfg.hermes_nudge_interval
        and hs["user_turns_since_review"] >= cfg.hermes_cooldown_turns
        and hs["reviews_this_session"] < cfg.hermes_max_reviews_per_session
    )
    assert should_trigger is False


def test_gating_triggers_when_all_conditions_met():
    """Verify trigger fires when all gates pass."""
    cfg = _make_config(hermes_nudge_interval=10, hermes_cooldown_turns=5,
                       hermes_max_pending=5, hermes_max_reviews_per_session=3)
    hs = {
        "iters_since_skill_manage": 12,
        "user_turns_since_review": 6,
        "reviews_this_session": 1,
    }
    should_trigger = (
        hs["iters_since_skill_manage"] >= cfg.hermes_nudge_interval
        and hs["user_turns_since_review"] >= cfg.hermes_cooldown_turns
        and hs["reviews_this_session"] < cfg.hermes_max_reviews_per_session
    )
    assert should_trigger is True


def test_gating_skips_when_interval_not_reached():
    """Verify trigger skips when tool call count is below interval."""
    cfg = _make_config(hermes_nudge_interval=10)
    hs = {
        "iters_since_skill_manage": 5,
        "user_turns_since_review": 10,
        "reviews_this_session": 0,
    }
    should_trigger = (
        hs["iters_since_skill_manage"] >= cfg.hermes_nudge_interval
        and hs["user_turns_since_review"] >= cfg.hermes_cooldown_turns
        and hs["reviews_this_session"] < cfg.hermes_max_reviews_per_session
    )
    assert should_trigger is False
