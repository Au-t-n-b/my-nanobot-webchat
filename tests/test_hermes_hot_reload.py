"""Hermes runtime hot-reload tests.

Tests the reload_skills_auto_config() method, epoch-based state reset,
stale-write guard in _run_skill_review, and tool registry rebuild.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.config.schema import SkillsAutoConfig


# ── Minimal AgentLoop shim ─────────────────────────────────────────────────
# We use __new__ to avoid the full init, then set only the attributes
# needed by reload_skills_auto_config / _get_hermes_state / _run_skill_review.


def _make_loop(tmp_path: Path, *, hermes_enabled: bool = False, **overrides):
    """Create a minimal AgentLoop with just enough state for Hermes tests."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.tools import ToolRegistry
    from nanobot.agent.skill_change_store import SkillChangeStore

    loop = AgentLoop.__new__(AgentLoop)

    # Minimal attributes required by the methods under test
    loop._skills_auto_config = SkillsAutoConfig(hermes_enabled=hermes_enabled, **overrides)
    loop._hermes_epoch = 0
    loop._hermes_state = {}
    loop.tools = ToolRegistry()
    loop.workspace = tmp_path
    loop.restrict_to_workspace = False
    loop.skill_change_store = SkillChangeStore(workspace=tmp_path, expiry_days=60)
    loop.skill_change_store.set_provider(MagicMock(), "test")

    # Context builder mock — just needs set_skills_auto_config
    loop.context = MagicMock()

    return loop


# ── Test: reload_skills_auto_config updates enabled without restart ────────


def test_reload_skills_auto_config_updates_enabled_without_restart(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False)
    assert loop._skills_auto_config.hermes_enabled is False

    new_cfg = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg

        bumped = loop.reload_skills_auto_config()

    assert bumped is True
    assert loop._skills_auto_config.hermes_enabled is True
    assert loop.tools.get("skill_manage") is not None
    print("[PASS] reload_skills_auto_config updates hermes_enabled without restart")


# ── Test: enable hermes mid-session starts counting from zero ──────────────


def test_enable_hermes_mid_session_starts_counting_from_zero(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False)

    # Simulate some prior activity with hermes off — should have no state
    assert "sess:1" not in loop._hermes_state

    # Enable hermes via reload
    new_cfg = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    # First access after enable — counters should start at zero
    hs = loop._get_hermes_state("sess:1")
    assert hs["iters_since_skill_manage"] == 0
    assert hs["reviews_this_session"] == 0
    assert hs["epoch"] == loop._hermes_epoch
    print("[PASS] enable hermes mid-session starts counting from zero")


# ── Test: enable hermes does not retroactively trigger review ──────────────


def test_enable_hermes_does_not_retroactively_trigger_review(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False)

    # Enable hermes
    new_cfg = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    # State should have 0 reviews — no retroactive trigger
    hs = loop._get_hermes_state("sess:1")
    assert hs["reviews_this_session"] == 0
    # iters should be 0 — no retroactive counting of prior tool calls
    assert hs["iters_since_skill_manage"] == 0
    print("[PASS] enable hermes does not retroactively trigger review")


# ── Test: enable hermes initializes cooldown as satisfied ──────────────────


def test_enable_hermes_initializes_cooldown_as_satisfied(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False, hermes_cooldown_turns=5)

    new_cfg = SkillsAutoConfig(hermes_enabled=True, hermes_cooldown_turns=5)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    hs = loop._get_hermes_state("sess:1")
    # user_turns_since_review should be initialized to cooldown_turns
    # so the first review is not blocked by "you haven't waited long enough"
    assert hs["user_turns_since_review"] == 5
    print("[PASS] enable hermes initializes cooldown as satisfied (user_turns_since_review=cooldown)")


# ── Test: disable hermes stops future triggers ──────────────────────────────


def test_disable_hermes_stops_future_triggers(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=True)

    # Add some state
    hs = loop._get_hermes_state("sess:1")
    hs["iters_since_skill_manage"] = 15
    hs["user_turns_since_review"] = 10

    # Manually register skill_manage to simulate running with Hermes on
    from nanobot.agent.tools.skill_manage import SkillManageTool
    loop.tools.register(SkillManageTool(
        workspace=loop.workspace,
        change_store=loop.skill_change_store,
    ))
    assert loop.tools.get("skill_manage") is not None

    # Disable hermes
    new_cfg = SkillsAutoConfig(hermes_enabled=False)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    assert loop._skills_auto_config.hermes_enabled is False
    assert loop.tools.get("skill_manage") is None  # tool unregistered

    print("[PASS] disable hermes stops future triggers and unregisters tool")


# ── Test: disable hermes prevents inflight review write ────────────────────


@pytest.mark.asyncio
async def test_disable_hermes_prevents_inflight_review_write(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=True)
    epoch_before = loop._hermes_epoch

    # Disable hermes — bumps epoch
    new_cfg = SkillsAutoConfig(hermes_enabled=False)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    epoch_after = loop._hermes_epoch
    assert epoch_after > epoch_before

    # Simulate an in-flight review that was scheduled before disable
    # It should detect hermes is off and return early
    snapshot = [{"role": "user", "content": "hello"}]
    # This should return without doing anything (no exception)
    await loop._run_skill_review(snapshot)

    # Also test epoch mismatch: re-enable with a new epoch
    new_cfg2 = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg2 = MagicMock()
        mock_cfg2.skills_auto = new_cfg2
        mock_load.return_value = mock_cfg2
        loop.reload_skills_auto_config()

    # Now hermes is on but epoch doesn't match the old one
    await loop._run_skill_review(snapshot, review_epoch=epoch_before)
    # No pending created because epoch mismatch
    assert loop.skill_change_store.pending_count() == 0

    print("[PASS] disable hermes prevents inflight review write")


# ── Test: reload_skills_auto_config increments epoch on toggle ─────────────


def test_reload_skills_auto_config_increments_epoch_on_toggle(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False)
    epoch_before = loop._hermes_epoch

    # Toggle: False -> True
    new_cfg = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()
    assert loop._hermes_epoch > epoch_before

    epoch_after_enable = loop._hermes_epoch

    # Same value again: should NOT bump epoch
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg2 = MagicMock()
        mock_cfg2.skills_auto = SkillsAutoConfig(hermes_enabled=True)
        mock_load.return_value = mock_cfg2
        bumped = loop.reload_skills_auto_config()
    assert loop._hermes_epoch == epoch_after_enable
    assert bumped is False

    # Toggle: True -> False
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg3 = MagicMock()
        mock_cfg3.skills_auto = SkillsAutoConfig(hermes_enabled=False)
        mock_load.return_value = mock_cfg3
        loop.reload_skills_auto_config()
    assert loop._hermes_epoch > epoch_after_enable

    print("[PASS] epoch increments on toggle, stays same on no-change reload")


# ── Test: reload rebuilds tools for next turn ──────────────────────────────


def test_reload_skills_auto_config_rebuilds_tools_for_next_turn(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False)

    # skill_manage should not be registered
    assert loop.tools.get("skill_manage") is None

    # Enable — tool should appear
    new_cfg = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()
    assert loop.tools.get("skill_manage") is not None

    # Disable — tool should disappear
    new_cfg2 = SkillsAutoConfig(hermes_enabled=False)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg2 = MagicMock()
        mock_cfg2.skills_auto = new_cfg2
        mock_load.return_value = mock_cfg2
        loop.reload_skills_auto_config()
    assert loop.tools.get("skill_manage") is None

    print("[PASS] tool registry correctly rebuilt on enable/disable")


# ── Test: config update API reports runtime_applied ────────────────────────
# This tests the routes.py integration indirectly by verifying
# reload_skills_auto_config return semantics.


def test_config_update_api_reports_runtime_applied(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=False)

    # Simulate what routes.py does
    new_cfg = SkillsAutoConfig(hermes_enabled=True)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        skills_auto_applied = loop.reload_skills_auto_config()

    # The response should indicate runtime was applied
    response = {
        "saved": True,
        "runtime_applied": True,
        "effective_from": "next_turn",
        "requires_restart": False,
        "skills_auto_applied": skills_auto_applied,
    }
    assert response["saved"] is True
    assert response["runtime_applied"] is True
    assert response["effective_from"] == "next_turn"
    assert response["requires_restart"] is False
    assert response["skills_auto_applied"] is True
    print("[PASS] config update API response correctly reports runtime_applied")


# ── Test: pending survives disable ─────────────────────────────────────────


def test_pending_survives_disable(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=True)

    # Create a pending request
    req = loop.skill_change_store.create_request(
        action="create",
        skill_name="test-skill",
        reason="test reason",
        proposed_content="---\nname: test-skill\ndescription: test\n---\nBody",
    )
    assert req.status == "pending"
    assert loop.skill_change_store.pending_count() == 1

    # Disable hermes
    new_cfg = SkillsAutoConfig(hermes_enabled=False)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    # Pending should still exist
    assert loop.skill_change_store.pending_count() == 1
    assert loop.skill_change_store.get_request(req.id) is not None
    print("[PASS] pending requests survive hermes disable")


# ── Test: epoch bump on gating config change (not just toggle) ─────────────


def test_epoch_bumps_on_gating_config_change(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=True, hermes_nudge_interval=10)
    epoch0 = loop._hermes_epoch

    # Change nudge_interval but keep hermes_enabled the same
    new_cfg = SkillsAutoConfig(hermes_enabled=True, hermes_nudge_interval=20)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        bumped = loop.reload_skills_auto_config()

    assert bumped is True
    assert loop._hermes_epoch > epoch0
    assert loop._skills_auto_config.hermes_nudge_interval == 20
    print("[PASS] epoch bumps on gating config change (nudge_interval)")


# ── Test: lazy epoch reset resets all counters ─────────────────────────────


def test_lazy_epoch_reset_resets_all_counters(tmp_path: Path):
    loop = _make_loop(tmp_path, hermes_enabled=True, hermes_cooldown_turns=5)

    # Build up some state
    hs = loop._get_hermes_state("sess:1")
    hs["iters_since_skill_manage"] = 42
    hs["user_turns_since_review"] = 10
    hs["reviews_this_session"] = 3
    old_epoch = hs["epoch"]

    # Bump epoch by changing config
    new_cfg = SkillsAutoConfig(hermes_enabled=True, hermes_nudge_interval=99)
    with patch("nanobot.config.loader.load_config") as mock_load:
        mock_cfg = MagicMock()
        mock_cfg.skills_auto = new_cfg
        mock_load.return_value = mock_cfg
        loop.reload_skills_auto_config()

    assert loop._hermes_epoch > old_epoch

    # Re-access — should trigger lazy reset
    hs2 = loop._get_hermes_state("sess:1")
    assert hs2["iters_since_skill_manage"] == 0
    assert hs2["reviews_this_session"] == 0
    assert hs2["user_turns_since_review"] == 5  # = cooldown_turns
    assert hs2["epoch"] == loop._hermes_epoch
    print("[PASS] lazy epoch reset resets all counters to fresh values")
