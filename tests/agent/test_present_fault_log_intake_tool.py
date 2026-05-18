"""Tests for ``present_fault_log_intake_card`` agent tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nanobot.agent.tools.fault_log_intake import PresentFaultLogIntakeCardTool
from nanobot.web.pending_hitl_store import PendingHitlStore


@pytest.mark.asyncio
async def test_present_fault_log_intake_creates_pending_and_replaces_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PendingHitlStore(tmp_path / "h.db")
    await store.init()

    calls: list[str] = []

    class FakeHandle:
        card_id = "card-fake"
        doc_id = "chat:thread-z"

    async def fake_ask_for_text_input(self, **kwargs):
        calls.append("ask_for_text_input")
        return FakeHandle()

    async def fake_replace_card(self, **kwargs):
        calls.append("replace_card")
        node = kwargs.get("node") or {}
        assert node.get("type") == "Stack"
        children = node.get("children") or []
        types = [c.get("type") for c in children if isinstance(c, dict)]
        assert "Markdown" in types
        assert "Tabs" in types
        assert "ConfirmCard" in types
        return FakeHandle()

    monkeypatch.setattr("nanobot.agent.loop.get_current_thread_id", lambda: "thread-z")
    monkeypatch.setattr("nanobot.agent.loop.get_pending_hitl_store", lambda: store)
    monkeypatch.setattr("nanobot.agent.loop.get_chat_docman", lambda: None)
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_text_input",
        fake_ask_for_text_input,
    )
    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.replace_card",
        fake_replace_card,
    )

    tool = PresentFaultLogIntakeCardTool()
    raw = await tool.execute(_nanobot_tool_call_id="tc-intake-1")
    data = json.loads(str(raw))
    assert data["ok"] is True
    assert data["requestId"]
    assert calls == ["ask_for_text_input", "replace_card"]

    row = await store.get_pending_request(str(data["requestId"]))
    assert row is not None
    assert row["resume_action"] == "agent_upload"
