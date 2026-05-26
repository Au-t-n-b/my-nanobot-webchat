"""Tests for context compact/persistence correctness fixes."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.memory import CompactResult, MemoryConsolidator
from nanobot.session.manager import Session


def _make_consolidator(tmp_path: Path, **overrides) -> MemoryConsolidator:
    from nanobot.providers.base import GenerationSettings

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings(max_tokens=4096)
    provider.chat_with_retry = AsyncMock(
        return_value=MagicMock(content="## Current State\nDone.\n## Worklog\n(empty)")
    )

    from nanobot.config.schema import ConsolidationConfig
    cfg = ConsolidationConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)

    from nanobot.session.manager import SessionManager
    sessions = SessionManager(tmp_path)

    return MemoryConsolidator(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        sessions=sessions,
        context_window_tokens=65536,
        build_messages=lambda **kw: [],
        get_tool_definitions=lambda: [],
        consolidation_config=cfg,
    )


class TestCompactLeafRangeBound:
    """Compact leaf must summarize only the archived chunk, not read session_memory."""

    @pytest.mark.asyncio
    async def test_compact_does_not_read_session_memory(self, tmp_path: Path) -> None:
        consolidator = _make_consolidator(tmp_path)
        mock_session_memory = MagicMock()
        mock_session_memory.read_summary = MagicMock(return_value="WRONG WHOLE-SESSION SUMMARY")
        consolidator.wire_subsystems(session_memory=mock_session_memory)

        session = Session(key="test:compact")
        for i in range(4):
            session.add_message("user", f"chunk_msg_{i}")
            session.add_message("assistant", f"chunk_reply_{i}")
        session.add_message("user", "retained_msg")
        session.add_message("assistant", "retained_reply")

        result = await consolidator.compact(session, trigger="auto", boundary_override=8)

        assert isinstance(result, CompactResult)
        assert result.success is True
        mock_session_memory.read_summary.assert_not_called()
        consolidator.provider.chat_with_retry.assert_awaited()


class TestCompactReturnType:
    """compact() must always return CompactResult, never bare True."""

    @pytest.mark.asyncio
    async def test_success_returns_compact_result(self, tmp_path: Path) -> None:
        consolidator = _make_consolidator(tmp_path)

        session = Session(key="test:return")
        for i in range(4):
            session.add_message("user", f"u{i}")
            session.add_message("assistant", f"a{i}")

        result = await consolidator.compact(session, trigger="auto", boundary_override=4)

        assert isinstance(result, CompactResult)
        assert result.success is True
        assert result.messages_archived == 4
        assert result.summary_preview  # non-empty

    @pytest.mark.asyncio
    async def test_failure_returns_compact_result_false(self, tmp_path: Path) -> None:
        consolidator = _make_consolidator(tmp_path)

        session = Session(key="test:fail")
        # Add a message so session.messages is non-empty (bypasses early-return),
        # but boundary_override=0 makes the chunk empty -> success=False.
        session.add_message("user", "only message")
        result = await consolidator.compact(session, trigger="auto", boundary_override=0)

        assert isinstance(result, CompactResult)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_range_id_populated_when_archive_exists(self, tmp_path: Path) -> None:
        consolidator = _make_consolidator(tmp_path)
        mock_archive = MagicMock()
        mock_archive.store_messages = MagicMock(return_value=42)
        consolidator.wire_subsystems(archive=mock_archive)

        session = Session(key="test:rangeid")
        for i in range(4):
            session.add_message("user", f"u{i}")
            session.add_message("assistant", f"a{i}")

        result = await consolidator.compact(session, trigger="auto", boundary_override=4)

        assert isinstance(result, CompactResult)
        assert result.success is True
        assert result.range_id == 42


class TestSessionMemoryDisabledByDefault:
    """SessionMemoryConfig.enabled should default to False."""

    def test_default_enabled_is_false(self) -> None:
        from nanobot.config.schema import SessionMemoryConfig
        cfg = SessionMemoryConfig()
        assert cfg.enabled is False

    def test_context_config_inherits_disabled(self) -> None:
        from nanobot.config.schema import ContextConfig
        cfg = ContextConfig()
        assert cfg.session_memory.enabled is False


class TestRecallContextConversationId:
    """RecallContextTool must know the current session key."""

    def test_set_context_stores_conversation_id(self) -> None:
        from nanobot.agent.tools.recall import RecallContextTool

        archive = MagicMock()
        archive.search_by_keyword = MagicMock(return_value=[])

        tool = RecallContextTool(archive)
        tool.set_context("web:abc123")

        tool._keyword_search({"query": "test", "limit": 5})

        archive.search_by_keyword.assert_called_once_with("web:abc123", "test", 5)

    def test_keyword_uses_injected_id_over_kwargs(self) -> None:
        from nanobot.agent.tools.recall import RecallContextTool

        archive = MagicMock()
        archive.search_by_keyword = MagicMock(return_value=[])

        tool = RecallContextTool(archive)
        tool.set_context("web:correct")
        tool._keyword_search({"query": "test", "_conversation_id": "web:wrong"})

        archive.search_by_keyword.assert_called_once_with("web:correct", "test", 10)

    def test_no_injected_id_falls_back_to_kwargs(self) -> None:
        from nanobot.agent.tools.recall import RecallContextTool

        archive = MagicMock()
        archive.search_by_keyword = MagicMock(return_value=[])

        tool = RecallContextTool(archive)
        # No set_context call — should fall back to kwargs
        tool._keyword_search({"query": "test", "_conversation_id": "web:fallback"})

        archive.search_by_keyword.assert_called_once_with("web:fallback", "test", 10)

    def test_set_context_accepts_thread_override_key(self) -> None:
        """Verify recall gets the real session key, not just channel:chat_id."""
        from nanobot.agent.tools.recall import RecallContextTool

        archive = MagicMock()
        archive.search_by_keyword = MagicMock(return_value=[])

        tool = RecallContextTool(archive)
        tool.set_context("web:thread-123")

        tool._keyword_search({"query": "test"})

        archive.search_by_keyword.assert_called_once_with("web:thread-123", "test", 10)


class TestReadFilePersistedOutput:
    """Large read_file results should be persisted, not blindly exempted."""

    def test_large_read_file_is_persisted(self, tmp_path: Path) -> None:
        from nanobot.agent.persisted_output import PersistedOutputManager
        from nanobot.config.schema import PersistedOutputConfig

        cfg = PersistedOutputConfig(size_threshold=500)
        mgr = PersistedOutputManager(tmp_path, cfg)

        large_content = "x" * 1000
        assert mgr.should_persist(large_content, "read_file", "call_123") is True

    def test_small_read_file_stays_inline(self, tmp_path: Path) -> None:
        from nanobot.agent.persisted_output import PersistedOutputManager
        from nanobot.config.schema import PersistedOutputConfig

        cfg = PersistedOutputConfig(size_threshold=500)
        mgr = PersistedOutputManager(tmp_path, cfg)

        small_content = "x" * 100
        assert mgr.should_persist(small_content, "read_file", "call_456") is False

    def test_persisted_output_contains_hint(self, tmp_path: Path) -> None:
        from nanobot.agent.persisted_output import PersistedOutputManager
        from nanobot.config.schema import PersistedOutputConfig

        cfg = PersistedOutputConfig(size_threshold=100, preview_head=50, preview_tail=50)
        mgr = PersistedOutputManager(tmp_path, cfg)

        content = "A" * 500
        preview = mgr.persist(content, "call_789", "read_file")

        assert "<persisted-output" in preview
        assert "grep/rg" in preview
        assert "read_file" in preview
        assert "offset" in preview
        assert "limit" in preview

    def test_read_file_not_in_exempt_tools_default(self) -> None:
        from nanobot.config.schema import PersistedOutputConfig
        cfg = PersistedOutputConfig()
        assert "read_file" not in cfg.exempt_tools

    def test_web_tools_still_exempt(self) -> None:
        from nanobot.config.schema import PersistedOutputConfig
        cfg = PersistedOutputConfig()
        assert "web_search" in cfg.exempt_tools
        assert "web_fetch" in cfg.exempt_tools


class TestCompactTiming:
    """Destructive compact must run in pre-turn, not background."""

    def test_metadata_flag_persistence(self, tmp_path: Path) -> None:
        """Verify metadata flag can be set and read back."""
        from nanobot.session.manager import SessionManager
        mgr = SessionManager(tmp_path)
        session = mgr.get_or_create("test:flag")
        session.metadata["compact_check_requested"] = True
        mgr.save(session)

        reloaded = mgr.get_or_create("test:flag")
        assert reloaded.metadata.get("compact_check_requested") is True

    def test_metadata_flag_pop(self, tmp_path: Path) -> None:
        """Verify flag is popped during processing."""
        session = Session(key="test:pop")
        session.metadata["compact_check_requested"] = True

        popped = session.metadata.pop("compact_check_requested", None)
        assert popped is True
        assert "compact_check_requested" not in session.metadata

    @pytest.mark.asyncio
    async def test_time_compact_checks_gap_correctly(self, tmp_path: Path) -> None:
        """Time-based compact should detect gap from OLD assistant, not just-written one."""
        consolidator = _make_consolidator(tmp_path)

        session = Session(key="test:timegap")
        old_ts = (datetime.now() - __import__("datetime").timedelta(hours=48)).isoformat()
        session.messages.append({
            "role": "user", "content": "old q", "timestamp": old_ts,
        })
        session.messages.append({
            "role": "assistant", "content": "old a", "timestamp": old_ts,
        })
        consolidator.sessions.save(session)

        # Verify gap detection
        from datetime import datetime as dt
        last_asst_ts = None
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant" and msg.get("timestamp"):
                last_asst_ts = msg["timestamp"]
                break
        last_dt = dt.fromisoformat(last_asst_ts)
        gap_hours = (dt.now() - last_dt).total_seconds() / 3600
        assert gap_hours >= 24


class TestConsolidationConfigWired:
    """Custom consolidation config should control compact behavior."""

    @pytest.mark.asyncio
    async def test_custom_max_rounds_respected(self, tmp_path: Path) -> None:
        from nanobot.config.schema import ConsolidationConfig
        cfg = ConsolidationConfig(max_rounds=1)
        consolidator = _make_consolidator(tmp_path, max_rounds=1)
        assert consolidator._consolidation_config.max_rounds == 1

    @pytest.mark.asyncio
    async def test_custom_trigger_percent(self, tmp_path: Path) -> None:
        consolidator = _make_consolidator(tmp_path, trigger_percent=80)
        assert consolidator._consolidation_config.trigger_percent == 80


class TestGetHistoryUnlimited:
    """get_history(max_messages=None) should return all unconsolidated legal history."""

    def test_none_returns_all(self) -> None:
        session = Session(key="test:unlimited")
        for i in range(10):
            session.add_message("user", f"q{i}")
            session.add_message("assistant", f"a{i}")

        history = session.get_history(max_messages=None)
        assert len(history) == 20

    def test_zero_returns_all_backward_compat(self) -> None:
        session = Session(key="test:zero")
        for i in range(10):
            session.add_message("user", f"q{i}")
            session.add_message("assistant", f"a{i}")

        history = session.get_history(max_messages=0)
        assert len(history) == 20

    def test_positive_limits(self) -> None:
        session = Session(key="test:limited")
        for i in range(10):
            session.add_message("user", f"q{i}")
            session.add_message("assistant", f"a{i}")

        history = session.get_history(max_messages=5)
        assert len(history) <= 5


class TestModuleFlowBoundary:
    """Compact must not split open module_skill_runtime flows."""

    def _make_module_tc(self, module_id: str, action: str) -> dict:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": f"tc_{module_id}_{action}",
                "type": "function",
                "function": {
                    "name": "module_skill_runtime",
                    "arguments": {
                        "module_id": module_id,
                        "action": action,
                    },
                },
            }],
        }

    def test_open_flow_detected(self) -> None:
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            {"role": "user", "content": "start module"},
            self._make_module_tc("mod_123", "start"),
            {"role": "tool", "tool_call_id": "tc_mod_123_start", "name": "module_skill_runtime", "content": "started"},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "working"},
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is True

    def test_finished_flow_not_detected(self) -> None:
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            {"role": "user", "content": "start module"},
            self._make_module_tc("mod_123", "start"),
            {"role": "tool", "tool_call_id": "tc_mod_123_start", "name": "module_skill_runtime", "content": "started"},
            self._make_module_tc("mod_123", "finish"),
            {"role": "tool", "tool_call_id": "tc_mod_123_finish", "name": "module_skill_runtime", "content": "done"},
            {"role": "user", "content": "next"},
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is False

    def test_normal_conversation_not_affected(self) -> None:
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "bye"},
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is False

    def test_multiple_modules_one_open(self) -> None:
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            self._make_module_tc("mod_1", "start"),
            self._make_module_tc("mod_1", "finish"),
            self._make_module_tc("mod_2", "start"),
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is True

    @pytest.mark.asyncio
    async def test_compact_skips_when_open_flow_at_boundary(self, tmp_path: Path) -> None:
        consolidator = _make_consolidator(tmp_path)

        session = Session(key="test:module_boundary")
        # Pre-fill with normal messages
        for i in range(4):
            session.add_message("user", f"u{i}")
            session.add_message("assistant", f"a{i}")
        # Open module flow starts but doesn't finish (near the boundary)
        session.messages.append(self._make_module_tc("mod_abc", "start"))
        session.messages.append({
            "role": "tool", "tool_call_id": "tc_mod_abc_start",
            "name": "module_skill_runtime", "content": "started",
        })
        session.add_message("user", "continue")
        session.add_message("assistant", "working")
        consolidator.sessions.save(session)

        # Compact with boundary that would split the open flow
        result = await consolidator.compact(session, trigger="auto", boundary_override=8)

        assert isinstance(result, CompactResult)
        # Should be skipped because open flow detected near boundary
        assert result.success is False

    def test_status_action_not_treated_as_open(self) -> None:
        """Non-start/waiting actions like 'status' should NOT mark open flow."""
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            self._make_module_tc("mod_x", "status"),
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is False

    def test_preview_action_not_treated_as_open(self) -> None:
        """'preview' should NOT mark open flow."""
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            self._make_module_tc("mod_x", "preview"),
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is False

    def test_upload_treated_as_open(self) -> None:
        """'upload' IS a start/waiting hint and should mark open flow."""
        from nanobot.agent.memory import MemoryConsolidator

        messages = [
            self._make_module_tc("mod_x", "upload"),
        ]

        assert MemoryConsolidator._has_open_module_flow(messages) is True
