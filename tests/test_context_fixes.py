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
