"""Tests for SQLite-backed pending HITL store (async resume)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def _now_ms() -> int:
    return int(time.time() * 1000)


@pytest.mark.asyncio
async def test_create_pending_hitl_is_idempotent_by_request_id(tmp_path: Path) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    envelope = {
        "event": "hitl.file_request",
        "threadId": "t-1",
        "skillName": "gongkan_skill",
        "skillRunId": "run-1",
        "payload": {
            "requestId": "req-1",
            "resumeAction": "run_step1",
            "onCancelAction": "cancel_step1_upload",
            "expiresAt": _now_ms() + 60_000,
            "cardId": "upload:1",
            "title": "请上传输入件",
        },
    }

    created_1 = await store.create_pending_request(envelope)
    created_2 = await store.create_pending_request(envelope)

    assert created_1 is True
    assert created_2 is False


@pytest.mark.asyncio
async def test_consume_result_is_idempotent_and_marks_consumed(tmp_path: Path) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.choice_request",
            "threadId": "t-1",
            "skillName": "m_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-choice-1",
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "expiresAt": _now_ms() + 60_000,
                "title": "请选择",
                "options": [{"id": "a", "label": "A"}],
            },
        }
    )

    result = {
        "type": "skill_runtime_result",
        "threadId": "t-1",
        "skillName": "m_skill",
        "skillRunId": "run-2",
        "requestId": "req-choice-1",
        "action": "after_choice",
        "status": "ok",
        "result": {"selected": "a"},
    }

    out_1 = await store.consume_result(result)
    out_2 = await store.consume_result(result)

    assert out_1["ok"] is True
    assert out_1["duplicate"] is False
    assert out_1["terminal_status"] == "consumed"

    assert out_2["ok"] is True
    assert out_2["duplicate"] is True
    assert out_2["terminal_status"] == "consumed"


@pytest.mark.asyncio
async def test_consume_result_accepts_skill_name_case_and_space_variants(tmp_path: Path) -> None:
    """Pending row may store disk slug; FilePicker may send UI-cased or spaced variants."""
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.file_request",
            "threadId": "t-zhgk",
            "skillName": "zhgk",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-upload-zhgk-1",
                "resumeAction": "zhgk_step1_scene_filter",
                "onCancelAction": "cancel_step1_upload",
                "expiresAt": _now_ms() + 60_000,
                "title": "上传",
            },
        }
    )

    result = {
        "type": "skill_runtime_result",
        "threadId": "t-zhgk",
        "skillName": "Zhgk",
        "skillRunId": "run-2",
        "requestId": "req-upload-zhgk-1",
        "status": "ok",
        "result": {"files": []},
    }
    out = await store.consume_result(result)
    assert out["ok"] is True
    assert out["duplicate"] is False

    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.file_request",
            "threadId": "t-gk",
            "skillName": "gongkan_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-upload-gk-1",
                "resumeAction": "step1",
                "onCancelAction": "cancel",
                "expiresAt": _now_ms() + 60_000,
                "title": "上传",
            },
        }
    )
    out2 = await store.consume_result(
        {
            "type": "skill_runtime_result",
            "threadId": "t-gk",
            "skillName": "gongkan skill",
            "skillRunId": "run-2",
            "requestId": "req-upload-gk-1",
            "status": "ok",
            "result": {},
        }
    )
    assert out2["ok"] is True


@pytest.mark.asyncio
async def test_consume_result_cancel_uses_fallback_routing_ignoring_client_action(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.confirm_request",
            "threadId": "t-1",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-confirm-1",
                "resumeAction": "approval_pass",
                "onCancelAction": "approval_defer",
                "expiresAt": _now_ms() + 60_000,
                "title": "确认继续",
            },
        }
    )

    cancel = {
        "type": "skill_runtime_result",
        "threadId": "t-1",
        "skillName": "s1",
        "skillRunId": "run-2",
        "requestId": "req-confirm-1",
        # malicious / wrong client action must be ignored for cancel
        "action": "approval_pass",
        "status": "cancel",
        "result": {"confirmed": False},
    }

    out = await store.consume_result(cancel)
    assert out["ok"] is True
    assert out["duplicate"] is False
    assert out["terminal_status"] == "consumed"

    replay = await store.get_result_for_request("req-confirm-1")
    assert replay is not None
    assert replay["action"] == "approval_defer"


@pytest.mark.asyncio
async def test_consume_result_error_uses_fallback_routing_ignoring_client_action(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.choice_request",
            "threadId": "t-1",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-choice-err-1",
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "expiresAt": _now_ms() + 60_000,
                "title": "请选择",
                "options": [{"id": "a", "label": "A"}],
            },
        }
    )

    err = {
        "type": "skill_runtime_result",
        "threadId": "t-1",
        "skillName": "s1",
        "skillRunId": "run-2",
        "requestId": "req-choice-err-1",
        # must be ignored for error
        "action": "after_choice",
        "status": "error",
        "result": {"code": "boom", "message": "something failed"},
    }

    out = await store.consume_result(err)
    assert out["ok"] is True
    assert out["duplicate"] is False
    assert out["terminal_status"] == "consumed"

    replay = await store.get_result_for_request("req-choice-err-1")
    assert replay is not None
    assert replay["action"] == "cancel_choice"


@pytest.mark.asyncio
async def test_consume_result_heals_stale_thread_id_when_pending(tmp_path: Path) -> None:
    """Pending rows created with a wrong thread_id (legacy driver/setdefault) align on consume."""
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.confirm_request",
            "threadId": "t-1",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-confirm-1",
                "resumeAction": "approval_pass",
                "onCancelAction": "approval_defer",
                "expiresAt": _now_ms() + 60_000,
                "title": "确认继续",
            },
        }
    )

    result = {
        "type": "skill_runtime_result",
        "threadId": "t-2",
        "skillName": "s1",
        "skillRunId": "run-2",
        "requestId": "req-confirm-1",
        "action": "approval_pass",
        "status": "ok",
        "result": {"confirmed": True},
    }

    out = await store.consume_result(result)
    assert out["ok"] is True
    assert out["duplicate"] is False
    assert out["terminal_status"] == "consumed"
    got = await store.get_pending_request("req-confirm-1")
    assert got is not None
    assert got["thread_id"] == "t-2"
    assert got["status"] == "consumed"


@pytest.mark.asyncio
async def test_consume_result_is_idempotent_when_terminal_and_thread_differs(tmp_path: Path) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.confirm_request",
            "threadId": "t-1",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-confirm-2",
                "resumeAction": "approval_pass",
                "onCancelAction": "approval_defer",
                "expiresAt": _now_ms() + 60_000,
                "title": "确认继续",
            },
        }
    )

    ok = {
        "type": "skill_runtime_result",
        "threadId": "t-1",
        "skillName": "s1",
        "requestId": "req-confirm-2",
        "status": "ok",
        "result": {"confirmed": True},
    }
    await store.consume_result(ok)

    bad_thread = {
        "type": "skill_runtime_result",
        "threadId": "t-9",
        "skillName": "s1",
        "requestId": "req-confirm-2",
        "status": "ok",
        "result": {"confirmed": True},
    }
    out_dup = await store.consume_result(bad_thread)
    assert out_dup["ok"] is True
    assert out_dup["duplicate"] is True
    assert out_dup["terminal_status"] == "consumed"


@pytest.mark.asyncio
async def test_timeout_resume_transitions_pending_to_timeout_and_is_idempotent(tmp_path: Path) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.file_request",
            "threadId": "t-1",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-file-expired",
                "resumeAction": "run_step1",
                "onCancelAction": "cancel_step1_upload",
                "expiresAt": _now_ms() - 1,
                "title": "请上传",
            },
        }
    )

    timed_1 = await store.timeout_expired_requests(now_ms=_now_ms())
    timed_2 = await store.timeout_expired_requests(now_ms=_now_ms())

    assert timed_1["timed_out_request_ids"] == ["req-file-expired"]
    assert timed_2["timed_out_request_ids"] == []

    # timeout should be recorded as a terminal status for idempotency/replay
    replay = await store.get_result_for_request("req-file-expired")
    assert replay is not None
    assert replay["status"] == "timeout"
    assert replay["action"] == "cancel_step1_upload"


@pytest.mark.asyncio
async def test_late_result_after_timeout_does_not_resume_twice(tmp_path: Path) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    db_path = tmp_path / "hitl.db"
    store = PendingHitlStore(db_path)
    await store.init()

    await store.create_pending_request(
        {
            "event": "hitl.choice_request",
            "threadId": "t-1",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-choice-expired",
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "expiresAt": _now_ms() - 1,
                "title": "请选择",
                "options": [{"id": "a", "label": "A"}],
            },
        }
    )

    timed = await store.timeout_expired_requests(now_ms=_now_ms())
    assert timed["timed_out_request_ids"] == ["req-choice-expired"]

    late = {
        "type": "skill_runtime_result",
        "threadId": "t-1",
        "skillName": "s1",
        "skillRunId": "run-2",
        "requestId": "req-choice-expired",
        "action": "after_choice",
        "status": "ok",
        "result": {"selected": "a"},
    }

    out = await store.consume_result(late)
    assert out["ok"] is True
    assert out["duplicate"] is True
    assert out["terminal_status"] == "timeout"

    # Deterministic replay still returns the timeout result.
    replay = await store.get_result_for_request("req-choice-expired")
    assert replay is not None
    assert json.loads(replay["result_json"]) == {"status": "timeout"}

