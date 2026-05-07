"""Tests for ``request_user_upload`` agent tool."""

from __future__ import annotations

import json

import pytest

from nanobot.agent.tools.user_upload import RequestUserUploadTool


@pytest.mark.asyncio
async def test_request_user_upload_invalid_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = RequestUserUploadTool()
    monkeypatch.setattr("nanobot.agent.loop.get_current_thread_id", lambda: "thread-x")
    monkeypatch.setattr("nanobot.agent.loop.get_pending_hitl_store", lambda: object())
    raw = await tool.execute(
        title="t",
        save_location_alias="not_a_real_alias",
        _nanobot_tool_call_id="tc-1",
    )
    data = json.loads(str(raw))
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_request_user_upload_invalid_relative_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = RequestUserUploadTool()
    monkeypatch.setattr("nanobot.agent.loop.get_current_thread_id", lambda: "thread-x")
    monkeypatch.setattr("nanobot.agent.loop.get_pending_hitl_store", lambda: object())
    raw = await tool.execute(
        title="t",
        save_relative_dir="../escape",
        _nanobot_tool_call_id="tc-1",
    )
    data = json.loads(str(raw))
    assert data["ok"] is False
    assert "invalid save_relative_dir" in str(data.get("error") or "")


@pytest.mark.asyncio
async def test_request_user_upload_creates_pending_and_emits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore

    store = PendingHitlStore(tmp_path / "h.db")
    await store.init()
    captured: dict = {}

    async def fake_ask_for_file(self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("nanobot.agent.loop.get_current_thread_id", lambda: "thread-y")
    monkeypatch.setattr("nanobot.agent.loop.get_pending_hitl_store", lambda: store)
    monkeypatch.setattr("nanobot.agent.loop.get_chat_docman", lambda: None)
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        fake_ask_for_file,
    )

    tool = RequestUserUploadTool()
    raw = await tool.execute(
        title="上传勘测表",
        purpose="survey",
        save_location_alias="zhgk_input",
        multiple=False,
        _nanobot_tool_call_id="tc-99",
    )
    data = json.loads(str(raw))
    assert data["ok"] is True
    assert data["status"] == "pending_user_upload"
    assert data["save_location_alias"] == "zhgk_input"
    assert captured.get("save_relative_dir") == "skills/zhgk/ProjectData/Input"
    assert captured.get("skill_name") == "nanobot_agent"
    assert captured.get("hitl_request_id")

    row = await store.get_pending_request(str(data["requestId"]))
    assert row is not None
    assert row["resume_action"] == "agent_upload"
