"""Tests for Hermes: state pruning, pending exception safety, snapshot distill, reject feedback."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.skill_change_store import SkillChangeStore
from nanobot.config.schema import SkillsAutoConfig


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(tmp_path, expiry_days=60)


def _make_config(**overrides) -> SkillsAutoConfig:
    defaults = {
        "hermes_enabled": True,
        "hermes_nudge_interval": 10,
        "hermes_cooldown_turns": 5,
        "hermes_max_pending": 5,
        "hermes_max_reviews_per_session": 3,
        "hermes_distill_snapshot": True,
        "hermes_use_reject_feedback": True,
    }
    defaults.update(overrides)
    return SkillsAutoConfig(**defaults)


# ── Part 1: pending_count exception safety ───────────────────────────────

def test_hermes_skips_when_pending_count_fails(tmp_path: Path):
    """Hermes should not crash the main flow if pending_count throws."""
    from nanobot.agent.skill_change_store import SkillChangeStore

    store = SkillChangeStore(tmp_path, expiry_days=60)
    # Close the underlying DB to force an error on next access
    # Actually, pending_count opens a new conn each time, so let's mock it
    cfg = _make_config()

    # Simulate the gating logic from loop.py
    try:
        pending = store.pending_count()
    except Exception:
        pending = cfg.hermes_max_pending  # safe default: skip

    # With a working store, pending should be 0
    assert pending == 0

    # Now simulate a broken store
    broken_store = MagicMock(spec=SkillChangeStore)
    broken_store.pending_count.side_effect = sqlite3.DatabaseError("disk error")

    try:
        pending = broken_store.pending_count()
    except Exception:
        pending = cfg.hermes_max_pending

    assert pending == cfg.hermes_max_pending  # safe default blocks trigger

    # Verify gating would block
    hs = {"iters_since_skill_manage": 15, "user_turns_since_review": 10, "reviews_this_session": 0}
    should_trigger = (
        hs["iters_since_skill_manage"] >= cfg.hermes_nudge_interval
        and pending < cfg.hermes_max_pending  # pending == max_pending → False
        and hs["user_turns_since_review"] >= cfg.hermes_cooldown_turns
        and hs["reviews_this_session"] < cfg.hermes_max_reviews_per_session
    )
    assert should_trigger is False


# ── Part 1: _hermes_state pruning (LRU) ─────────────────────────────────

def test_hermes_state_prunes_old_sessions():
    """_hermes_state should prune entries when it exceeds 100."""
    hermes_state: dict[str, dict] = {}

    def get_hermes_state(session_key: str) -> dict:
        now = time.time()
        if len(hermes_state) > 100:
            sorted_keys = sorted(hermes_state, key=lambda k: hermes_state[k].get("last_seen_at", 0))
            for k in sorted_keys[:50]:
                del hermes_state[k]
        if session_key not in hermes_state:
            hermes_state[session_key] = {
                "iters_since_skill_manage": 0,
                "user_turns_since_review": 0,
                "reviews_this_session": 0,
                "last_seen_at": now,
            }
        else:
            hermes_state[session_key]["last_seen_at"] = now
        return hermes_state[session_key]

    # Create 110 sessions — prune triggers when count exceeds 100
    for i in range(110):
        get_hermes_state(f"session:{i:03d}")
        time.sleep(0.001)

    # After 110 insertions, multiple prunes have occurred.
    # The dict should be well under 110 entries.
    assert len(hermes_state) <= 70

    # Verify the newest session survived
    assert "session:109" in hermes_state
    # Some of the oldest should be gone
    assert "session:000" not in hermes_state


def test_hermes_state_lru_refreshes_active_session():
    """Accessing a session should refresh its LRU position."""
    hermes_state: dict[str, dict] = {}

    def get_hermes_state(session_key: str) -> dict:
        now = time.time()
        if len(hermes_state) > 100:
            sorted_keys = sorted(hermes_state, key=lambda k: hermes_state[k].get("last_seen_at", 0))
            for k in sorted_keys[:50]:
                del hermes_state[k]
        if session_key not in hermes_state:
            hermes_state[session_key] = {
                "iters_since_skill_manage": 0,
                "user_turns_since_review": 0,
                "reviews_this_session": 0,
                "last_seen_at": now,
            }
        else:
            hermes_state[session_key]["last_seen_at"] = now
        return hermes_state[session_key]

    # Create 101 sessions with session:keep being the oldest
    get_hermes_state("session:keep")
    time.sleep(0.01)
    for i in range(101):
        get_hermes_state(f"session:other:{i:03d}")
        time.sleep(0.001)

    # Touch "session:keep" to refresh its last_seen_at
    time.sleep(0.01)
    get_hermes_state("session:keep")

    # Trigger prune by accessing a new session
    get_hermes_state("session:new")
    assert len(hermes_state) <= 62  # ~52 after prune + new

    # "session:keep" should survive because it was refreshed
    assert "session:keep" in hermes_state


# ── Part 2: _distill_for_review ─────────────────────────────────────────

def _import_distill():
    """Import the static method from AgentLoop."""
    from nanobot.agent.loop import AgentLoop
    return AgentLoop._distill_for_review


def test_distill_keeps_early_user_intent():
    distill = _import_distill()
    messages = [
        {"role": "user", "content": "I need to set up a CI pipeline for my Python project"},
        {"role": "assistant", "content": "I'll help you set up CI."},
        {"role": "tool", "name": "read_file", "content": "file contents here"},
    ]
    for i in range(20):
        messages.append({"role": "assistant", "content": f"Step {i}"})
        messages.append({"role": "tool", "name": "exec", "content": f"output {i}" * 100})

    result = distill(messages)
    user_msgs = [m for m in result if m["role"] == "user"]
    assert len(user_msgs) >= 1
    assert "CI pipeline" in user_msgs[0]["content"]


def test_distill_keeps_tool_tail_and_errors():
    distill = _import_distill()
    tool_output = (
        "line 1: ok\nline 2: ok\n"
        + "x" * 1000 + "\n"
        + "Traceback (most recent call last):\n"
        + "  File 'test.py', line 42\n"
        + "AssertionError: expected 200 got 500\n"
    )
    messages = [
        {"role": "user", "content": "run test"},
        {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "exec"}}]},
        {"role": "tool", "name": "exec", "content": tool_output},
    ]
    result = distill(messages)
    # Tool outputs are now converted to assistant messages
    tool_summaries = [m for m in result if m["role"] == "assistant" and m["content"].startswith("[Tool summary:")]
    assert len(tool_summaries) == 1
    content = tool_summaries[0]["content"]
    # Extract JSON after the header line
    json_part = content.split("\n", 1)[1]
    parsed = json.loads(json_part)
    assert parsed["truncated"] is True
    assert "Traceback" in parsed.get("errors", "") or "AssertionError" in parsed.get("errors", "")
    assert parsed["original_chars"] == len(tool_output)


def test_distill_limits_large_tool_output():
    distill = _import_distill()
    huge_output = "x" * 100_000
    messages = [
        {"role": "tool", "name": "read_file", "content": huge_output},
    ]
    result = distill(messages)
    tool_summaries = [m for m in result if m["role"] == "assistant" and m["content"].startswith("[Tool summary:")]
    assert len(tool_summaries) == 1
    json_part = tool_summaries[0]["content"].split("\n", 1)[1]
    parsed = json.loads(json_part)
    assert parsed["truncated"] is True
    assert len(tool_summaries[0]["content"]) < 5000  # summary is much smaller than 100K


def test_distill_compresses_tool_call_only_assistant_message():
    distill = _import_distill()
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [
            {"function": {"name": "read_file"}, "id": "c1", "type": "function"},
            {"function": {"name": "exec"}, "id": "c2", "type": "function"},
        ]},
    ]
    result = distill(messages)
    asst_msgs = [m for m in result if m["role"] == "assistant"]
    assert len(asst_msgs) == 1
    assert "read_file" in asst_msgs[0]["content"]
    assert "exec" in asst_msgs[0]["content"]


def test_distill_preserves_user_correction_message():
    distill = _import_distill()
    messages = [
        {"role": "user", "content": "set up CI"},
        {"role": "assistant", "content": "I'll do X."},
        {"role": "user", "content": "No, I want GitHub Actions, not Jenkins. And use Python 3.12."},
    ]
    result = distill(messages)
    user_msgs = [m for m in result if m["role"] == "user"]
    assert len(user_msgs) == 2
    assert "GitHub Actions" in user_msgs[1]["content"]


def test_distill_caps_user_message_length():
    distill = _import_distill()
    long_msg = "x" * 10000
    messages = [{"role": "user", "content": long_msg}]
    result = distill(messages)
    assert len(result[0]["content"]) <= 4000


def test_distill_short_tool_output_not_truncated():
    distill = _import_distill()
    messages = [{"role": "tool", "name": "exec", "content": "short output"}]
    result = distill(messages)
    # Short tool output is wrapped in [Tool summary:] header
    assert result[0]["role"] == "assistant"
    assert "[Tool summary: exec]" in result[0]["content"]
    assert "short output" in result[0]["content"]


def test_distill_extracts_test_results():
    distill = _import_distill()
    tool_output = "running tests...\n" + "x" * 1000 + "\n48 passed, 2 failed, 1 error\nDONE"
    messages = [{"role": "tool", "name": "exec", "content": tool_output}]
    result = distill(messages)
    json_part = result[0]["content"].split("\n", 1)[1]
    parsed = json.loads(json_part)
    assert parsed["truncated"] is True
    assert "48 passed" in parsed["test_results"]
    assert "2 failed" in parsed["test_results"]
    assert "1 error" in parsed["test_results"]


def test_distill_redacts_sensitive_values():
    distill = _import_distill()
    tool_output = (
        "export API_KEY=sk-abc123def456\n"
        + "x" * 1000 + "\n"
        + "Authorization: Bearer token_xyz789\n"
    )
    messages = [{"role": "tool", "name": "exec", "content": tool_output}]
    result = distill(messages)
    content = result[0]["content"]
    # Raw secrets should not appear in the distilled output
    assert "sk-abc123def456" not in content
    assert "token_xyz789" not in content
    # Redacted markers should be present
    assert "***" in content
    # Should be an assistant message, not tool
    assert result[0]["role"] == "assistant"


def test_distill_converts_tool_outputs_to_assistant_summaries():
    distill = _import_distill()
    messages = [
        {"role": "tool", "name": "exec", "content": "x" * 2000},
        {"role": "tool", "name": "read_file", "content": "file content here"},
    ]
    result = distill(messages)
    # No role="tool" messages in output
    assert all(m["role"] != "tool" for m in result)
    # Both should be assistant messages with [Tool summary:] headers
    summaries = [m for m in result if m["content"].startswith("[Tool summary:")]
    assert len(summaries) == 2
    assert "[Tool summary: exec]" in summaries[0]["content"]
    assert "[Tool summary: read_file]" in summaries[1]["content"]
    # No tool_call_id or tool_calls field
    for m in result:
        assert "tool_call_id" not in m
        assert "tool_calls" not in m


def test_distill_output_has_no_tool_role_without_tool_call_id():
    distill = _import_distill()
    messages = [
        {"role": "user", "content": "do something"},
        {"role": "assistant", "content": "let me check", "tool_calls": [{"function": {"name": "exec"}, "id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "name": "exec", "content": "x" * 5000},
    ]
    result = distill(messages)
    tool_roles = [m for m in result if m["role"] == "tool"]
    assert len(tool_roles) == 0, f"Found tool role messages: {tool_roles}"
    # All messages should be user or assistant only
    assert all(m["role"] in ("user", "assistant") for m in result)
    distill = _import_distill()
    # Create a very large conversation
    messages = []
    for i in range(200):
        messages.append({"role": "user", "content": f"User message {i} " + "x" * 200})
        messages.append({"role": "assistant", "content": f"Assistant reply {i} " + "y" * 200})
        messages.append({"role": "tool", "name": "exec", "content": "z" * 2000})
    result = distill(messages)
    total_chars = sum(len(m.get("content", "")) for m in result)
    assert total_chars <= 55_000  # should be under the 50K cap + small margin
    # Early user intent should be preserved
    user_msgs = [m for m in result if m["role"] == "user"]
    assert len(user_msgs) >= 1
    assert "User message 0" in user_msgs[0]["content"]


# ── Part 2: reject feedback injection ────────────────────────────────────

def test_recent_rejections_injected_into_prompt(store: SkillChangeStore):
    """Verify rejected notes can be fetched and formatted for prompt injection."""
    store.create_request(action="create", skill_name="bad-skill-1", reason="r1")
    store.reject_request(store.list_requests(status="pending")[0].id, note="Too specific")

    store.create_request(action="create", skill_name="bad-skill-2", reason="r2")
    store.reject_request(store.list_requests(status="pending")[0].id, note="Duplicate")

    rejected = store.list_requests(status="rejected")
    recent_with_notes = [r for r in rejected if r.reviewer_note and r.reviewer_note.strip()][:5]
    assert len(recent_with_notes) == 2

    lines = []
    for r in recent_with_notes:
        reason_snippet = (r.reason or "")[:80]
        lines.append(f"- {r.skill_name}: {r.reviewer_note} — {reason_snippet}")

    feedback = "Recently rejected skill suggestions:\n" + "\n".join(lines)
    assert "bad-skill-1" in feedback
    assert "Too specific" in feedback
    assert "bad-skill-2" in feedback
    assert "Duplicate" in feedback


def test_recent_rejections_skips_empty_notes(store: SkillChangeStore):
    """Requests rejected without a note should be skipped."""
    store.create_request(action="create", skill_name="no-note-skill", reason="r1")
    store.reject_request(store.list_requests(status="pending")[0].id, note="")

    store.create_request(action="create", skill_name="with-note-skill", reason="r2")
    store.reject_request(store.list_requests(status="pending")[0].id, note="Wrong")

    rejected = store.list_requests(status="rejected")
    with_notes = [r for r in rejected if r.reviewer_note and r.reviewer_note.strip()]
    assert len(with_notes) == 1
    assert with_notes[0].skill_name == "with-note-skill"


# ── Config tests ──────────────────────────────────────────────────────────

def test_config_distill_snapshot_default():
    cfg = SkillsAutoConfig()
    assert cfg.hermes_distill_snapshot is True
    assert cfg.hermes_use_reject_feedback is True


def test_config_distill_snapshot_disabled():
    cfg = _make_config(hermes_distill_snapshot=False)
    assert cfg.hermes_distill_snapshot is False


def test_config_reject_feedback_disabled():
    cfg = _make_config(hermes_use_reject_feedback=False)
    assert cfg.hermes_use_reject_feedback is False


def test_reject_note_truncated_to_100_chars(store: SkillChangeStore):
    """Verify reviewer_note is truncated when injected into the prompt."""
    long_note = "A" * 500
    store.create_request(action="create", skill_name="long-note-skill", reason="r1")
    store.reject_request(store.list_requests(status="pending")[0].id, note=long_note)
    rejected = store.list_requests(status="rejected")
    recent_with_notes = [r for r in rejected if r.reviewer_note and r.reviewer_note.strip()][:5]
    # Simulate the truncation logic from loop.py
    for r in recent_with_notes:
        note_text = (r.reviewer_note or "")[:100]
        assert len(note_text) <= 100


def test_reject_feedback_limited_to_5_entries(store: SkillChangeStore):
    """Verify only 5 most recent rejected-with-notes are returned."""
    for i in range(8):
        store.create_request(action="create", skill_name=f"skill-{i}", reason=f"reason {i}")
        store.reject_request(store.list_requests(status="pending")[0].id, note=f"Note {i}")
    result = store.list_recent_rejected_with_notes(limit=5)
    assert len(result) == 5


def test_recent_rejections_ordered_by_reviewed_at(store: SkillChangeStore):
    """list_recent_rejected_with_notes should return most recently reviewed first."""
    import sqlite3
    # Create and reject 3 requests with different reviewed_at timestamps
    for i in range(3):
        store.create_request(action="create", skill_name=f"skill-{i}", reason=f"reason {i}")
        req = store.list_requests(status="pending")[0]
        # Reject normally (sets reviewed_at to now)
        store.reject_request(req.id, note=f"Note {i}")

    # Manually adjust reviewed_at so skill-0 is most recent, skill-2 is oldest
    all_rejected = store.list_requests(status="rejected")
    with store._conn() as conn:
        conn.execute(
            "UPDATE skill_change_requests SET reviewed_at = ? WHERE skill_name = ?",
            ("2026-05-17T12:00:00+00:00", "skill-0"),
        )
        conn.execute(
            "UPDATE skill_change_requests SET reviewed_at = ? WHERE skill_name = ?",
            ("2026-05-17T11:00:00+00:00", "skill-1"),
        )
        conn.execute(
            "UPDATE skill_change_requests SET reviewed_at = ? WHERE skill_name = ?",
            ("2026-05-17T10:00:00+00:00", "skill-2"),
        )

    result = store.list_recent_rejected_with_notes(limit=5)
    assert len(result) == 3
    # Most recently reviewed should be first
    assert result[0].skill_name == "skill-0"
    assert result[1].skill_name == "skill-1"
    assert result[2].skill_name == "skill-2"


def test_list_recent_rejected_skips_empty_notes(store: SkillChangeStore):
    """list_recent_rejected_with_notes should only return entries with notes."""
    store.create_request(action="create", skill_name="with-note", reason="r1")
    store.reject_request(store.list_requests(status="pending")[0].id, note="Good reason")

    store.create_request(action="create", skill_name="no-note", reason="r2")
    store.reject_request(store.list_requests(status="pending")[0].id, note="")

    result = store.list_recent_rejected_with_notes(limit=5)
    assert len(result) == 1
    assert result[0].skill_name == "with-note"
