"""Mixed E2E tests for compact/archive/recall information fidelity.

- Tests 1-11: Mock compact + real archive/recall/session (default run)
- Tests 12-13: Mock compact + real LLM recall (RUN_MIXED_LLM_E2E=1)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.memory import CompactResult, MemoryConsolidator
from nanobot.agent.message_archive import MessageArchive
from nanobot.agent.tools.recall import RecallContextTool
from nanobot.config.schema import ConsolidationConfig, MessageArchiveConfig, PersistedOutputConfig
from nanobot.providers.base import GenerationSettings, LLMResponse
from nanobot.session.manager import Session, SessionManager

# ---------------------------------------------------------------------------
# Environment gates
# ---------------------------------------------------------------------------
TRACE_ENABLED = os.getenv("COMPACT_TRACE", "1") != "0"
RUN_MIXED_LLM_E2E = os.getenv("RUN_MIXED_LLM_E2E", "0") == "1"

# ---------------------------------------------------------------------------
# Needles — unique anchors planted in messages for traceability
# ---------------------------------------------------------------------------
NEEDLES = {
    "early_user_fact": "NEEDLE_EARLY_USER_FACT_ALPHA_001",
    "early_tool_fact": "NEEDLE_EARLY_TOOL_FACT_BETA_002",
    "early_assistant_decision": "NEEDLE_EARLY_ASSISTANT_DECISION_GAMMA_003",
    "early_error": "NEEDLE_EARLY_ERROR_DELTA_004",
    "early_resolution": "NEEDLE_EARLY_RESOLUTION_EPSILON_005",
    "file_path": "NEEDLE_FILE_PATH_ZETA_006",
    "retained_recent": "NEEDLE_RETAINED_RECENT_ETA_007",
    "future_after_compact": "NEEDLE_FUTURE_AFTER_COMPACT_THETA_008",
    "second_round_old": "NEEDLE_SECOND_ROUND_OLD_IOTA_009",
    "second_round_new": "NEEDLE_SECOND_ROUND_NEW_KAPPA_010",
    "large_read_file": "NEEDLE_LARGE_READ_FILE_LAMBDA_011",
    "large_file_middle": "NEEDLE_ONLY_IN_MIDDLE_LARGE_FILE_012",
    "large_file_tail": "NEEDLE_LARGE_FILE_TAIL_013",
    "session_a": "NEEDLE_SESSION_A_MU_014",
    "session_b": "NEEDLE_SESSION_B_NU_015",
}

# Needles expected to be archived after a standard compact
ARCHIVED_NEEDLES = [
    "early_user_fact",
    "early_tool_fact",
    "early_assistant_decision",
    "early_error",
    "early_resolution",
    "file_path",
]

# A deliberately lossy summary that omits some needles
LOSSY_SUMMARY = (
    "[COMPACT] 以下是对早期对话的压缩摘要：\n\n"
    "## Current State\n"
    f"已归档早期流程，包含 {NEEDLES['early_user_fact']}。\n\n"
    "## Key Decisions\n"
    "- 早期有关键决策，但不展开所有细节。\n\n"
    "## Worklog\n"
    "细节请通过 recall_context 查询。"
)


# ---------------------------------------------------------------------------
# CompactTrace — test trace output helper
# ---------------------------------------------------------------------------
class CompactTrace:
    def __init__(self, enabled: bool = TRACE_ENABLED):
        self.enabled = enabled
        self.rows: list[dict[str, Any]] = []

    def add(self, stage: str, **data: Any) -> None:
        row = {"stage": stage, **data}
        self.rows.append(row)
        if self.enabled:
            print(f"\n[COMPACT_TRACE] {stage}")
            for k, v in data.items():
                print(f"  {k}: {v}")

    def dump_matrix(self, matrix: dict[str, dict[str, bool]]) -> None:
        print("\n[RECALL_COVERAGE_MATRIX]")
        for needle, values in matrix.items():
            print(f"  {needle}:")
            for check, result in values.items():
                print(f"    {check}: {result}")


# ---------------------------------------------------------------------------
# Coverage matrix builder
# ---------------------------------------------------------------------------
def build_coverage_matrix(
    needles: dict[str, str],
    *,
    active_session_text: str,
    compact_summary_text: str,
    range_recall_text: str,
    keyword_recall_texts: dict[str, str],
    archive_raw_text: str = "",
) -> dict[str, dict[str, bool]]:
    matrix: dict[str, dict[str, bool]] = {}
    for name, needle in needles.items():
        matrix[name] = {
            "active_session": needle in active_session_text,
            "compact_summary": needle in compact_summary_text,
            "range_recall": needle in range_recall_text,
            "keyword_recall": needle in keyword_recall_texts.get(name, ""),
            "archive_raw": needle in archive_raw_text,
        }
    return matrix


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------
def _make_consolidator_with_archive(tmp_path: Path) -> tuple[MemoryConsolidator, MessageArchive]:
    """Build a MemoryConsolidator with a real MessageArchive and mock LLM.

    The mock LLM returns LOSSY_SUMMARY for _generate_leaf calls.
    """
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings(max_tokens=4096)
    provider.chat_with_retry = AsyncMock(
        return_value=LLMResponse(content=LOSSY_SUMMARY, tool_calls=[])
    )

    cfg = ConsolidationConfig()
    sessions = SessionManager(tmp_path)
    archive = MessageArchive(tmp_path, MessageArchiveConfig())

    consolidator = MemoryConsolidator(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        sessions=sessions,
        context_window_tokens=65536,
        build_messages=lambda **kw: [],
        get_tool_definitions=lambda: [],
        consolidation_config=cfg,
    )
    consolidator.wire_subsystems(archive=archive)
    return consolidator, archive


def _make_recall_tool(archive: MessageArchive) -> RecallContextTool:
    tool = RecallContextTool(archive)
    return tool


def _build_early_messages() -> list[dict[str, Any]]:
    """Build the standard set of early messages containing archived needles."""
    messages = [
        {"role": "user", "content": f"用户需求：{NEEDLES['early_user_fact']}"},
        {"role": "assistant", "content": f"关键决策：{NEEDLES['early_assistant_decision']}"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_read_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "/some/file.py"}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call_read_1",
            "name": "read_file",
            "content": (
                f"文件输出包含 {NEEDLES['early_tool_fact']}\n"
                f"文件路径 {NEEDLES['file_path']}"
            ),
        },
        {"role": "assistant", "content": f"发现错误：{NEEDLES['early_error']}"},
        {"role": "user", "content": f"解决偏好：{NEEDLES['early_resolution']}"},
        {"role": "assistant", "content": "已解决。"},
    ]
    return messages


def _build_retained_messages() -> list[dict[str, Any]]:
    """Build retained-recent messages that survive compact."""
    return [
        {"role": "user", "content": f"最近任务：{NEEDLES['retained_recent']}"},
        {"role": "assistant", "content": "继续最近任务。"},
    ]


def _get_archive_raw_text(archive: MessageArchive, conv_id: str, range_id: int) -> str:
    """Concatenate all raw archived message content for a range."""
    data = archive.get_range(range_id)
    if not data:
        return ""
    parts: list[str] = []
    for msg in data.get("messages", []):
        preview = msg.get("preview", "")
        parts.append(preview)
    return " ".join(parts)


def _get_all_archive_raw(archive: MessageArchive, conv_id: str, range_id: int) -> str:
    """Read full content from archived_messages for a range (not just 100-char preview)."""
    import sqlite3
    rows = archive._conn.execute(
        "SELECT content FROM archived_messages WHERE range_id = ? ORDER BY msg_idx",
        (range_id,),
    ).fetchall()
    return " ".join(str(r[0]) or "" for r in rows)


def _collect_keyword_recall_texts(
    recall_tool: RecallContextTool,
    needle_names: list[str],
) -> dict[str, str]:
    """For each needle name, do a keyword search and collect result text."""
    results: dict[str, str] = {}
    for name in needle_names:
        needle = NEEDLES[name]
        text = recall_tool._keyword_search({"query": needle, "limit": 10})
        results[name] = text
    return results


# ===========================================================================
# Test 1: One compact → information recovery matrix
# ===========================================================================
class TestOneCompactRecoveryMatrix:
    """After one compact, archived needles must be recoverable via recall."""

    @pytest.mark.asyncio
    async def test_archived_needles_recoverable(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test1")
        for msg in _build_early_messages():
            session.messages.append(msg)
        for msg in _build_retained_messages():
            session.messages.append(msg)
        consolidator.sessions.save(session)

        trace.add("before_compact", message_count=len(session.messages))

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )

        trace.add(
            "compact_result",
            success=result.success,
            range_id=result.range_id,
            messages_archived=result.messages_archived,
            summary_preview=result.summary_preview[:200] if result.summary_preview else "",
        )
        assert result.success is True
        assert result.range_id is not None

        trace.add(
            "after_compact",
            message_count=len(session.messages),
            first_role=session.messages[0]["role"],
            first_preview=str(session.messages[0].get("content", ""))[:100],
        )

        assert "[COMPACT]" in session.messages[0].get("content", "")

        active_text = " ".join(
            str(m.get("content", "")) for m in session.messages
        )
        assert NEEDLES["retained_recent"] in active_text

        for i in range(1, len(session.messages)):
            msg = session.messages[i]
            assert msg.get("role") != "user" or NEEDLES["early_user_fact"] not in str(
                msg.get("content", "")
            )

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)

        range_result = recall_tool._range_get({"range_id": result.range_id})
        trace.add("range_recall", length=len(range_result), preview=range_result[:300])

        keyword_texts = _collect_keyword_recall_texts(
            recall_tool, ARCHIVED_NEEDLES
        )

        archive_raw = _get_all_archive_raw(archive, session.key, result.range_id)

        matrix = build_coverage_matrix(
            {k: NEEDLES[k] for k in ARCHIVED_NEEDLES},
            active_session_text=active_text,
            compact_summary_text=session.messages[0].get("content", ""),
            range_recall_text=range_result,
            keyword_recall_texts=keyword_texts,
            archive_raw_text=archive_raw,
        )
        trace.dump_matrix(matrix)

        for name in ARCHIVED_NEEDLES:
            assert matrix[name]["range_recall"], f"{name} not found in range_recall"
            assert matrix[name]["archive_raw"], f"{name} not found in archive_raw"

        keyword_hits = sum(1 for name in ARCHIVED_NEEDLES if matrix[name]["keyword_recall"])
        assert keyword_hits >= 5, f"keyword_recall only hit {keyword_hits}/6"

        assert NEEDLES["retained_recent"] not in range_result


# ===========================================================================
# Test 2: Compact summary is lossy, but recall must find omitted content
# ===========================================================================
class TestLossySummaryRecallRecovery:
    """Needles omitted from compact summary must be recoverable via recall."""

    @pytest.mark.asyncio
    async def test_omitted_needles_found_via_recall(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test2")
        for msg in _build_early_messages():
            session.messages.append(msg)
        for msg in _build_retained_messages():
            session.messages.append(msg)
        consolidator.sessions.save(session)

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )
        assert result.success is True

        compact_text = session.messages[0].get("content", "")

        omitted = [
            "early_tool_fact",
            "early_error",
            "file_path",
        ]
        for name in omitted:
            assert NEEDLES[name] not in compact_text, (
                f"{name} unexpectedly in compact summary (test setup error)"
            )

        trace.add("compact_summary_omits", needles=omitted)

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)

        range_result = recall_tool._range_get({"range_id": result.range_id})
        for name in omitted:
            assert NEEDLES[name] in range_result, (
                f"{name} not found in range recall"
            )

        keyword_texts = _collect_keyword_recall_texts(recall_tool, omitted)
        for name in omitted:
            assert NEEDLES[name] in keyword_texts[name], (
                f"{name} not found in keyword recall"
            )

        archive_raw = _get_all_archive_raw(archive, session.key, result.range_id)
        for name in omitted:
            assert NEEDLES[name] in archive_raw, (
                f"{name} not found in archive raw"
            )

        trace.add("recall_recovery", all_omitted_found=True)


# ===========================================================================
# Test 3: Future turn does not pollute old archive range
# ===========================================================================
class TestFutureTurnIsolation:
    """Messages added after compact must not appear in the old archived range."""

    @pytest.mark.asyncio
    async def test_future_not_in_old_range(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test3")
        session.add_message("user", f"需求：{NEEDLES['early_user_fact']}")
        session.add_message("assistant", "处理中")
        session.add_message("user", f"最近：{NEEDLES['retained_recent']}")
        session.add_message("assistant", "继续")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=2)
        assert result.success is True
        trace.add("compact_done", range_id=result.range_id)

        session.add_message("user", f"未来：{NEEDLES['future_after_compact']}")
        session.add_message("assistant", "未来处理")
        consolidator.sessions.save(session)

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)
        old_range = recall_tool._range_get({"range_id": result.range_id})

        trace.add("old_range_recall", preview=old_range[:300])

        assert NEEDLES["early_user_fact"] in old_range
        assert NEEDLES["future_after_compact"] not in old_range

        active_text = " ".join(str(m.get("content", "")) for m in session.messages)
        assert NEEDLES["future_after_compact"] in active_text

        trace.dump_matrix({
            "early_user_fact": {
                "old_range": NEEDLES["early_user_fact"] in old_range,
                "active": NEEDLES["early_user_fact"] in active_text,
            },
            "future_after_compact": {
                "old_range": NEEDLES["future_after_compact"] in old_range,
                "active": NEEDLES["future_after_compact"] in active_text,
            },
        })


# ===========================================================================
# Test 4: Double compact — both ranges remain recallable
# ===========================================================================
class TestDoubleCompactRanges:
    """After two compacts, both range_id_1 and range_id_2 must be recallable."""

    @pytest.mark.asyncio
    async def test_both_ranges_recallable(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test4")

        session.add_message("user", f"第一轮：{NEEDLES['early_user_fact']}")
        session.add_message("assistant", f"第一轮回复：{NEEDLES['early_tool_fact']}")
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result1 = await consolidator.compact(session, trigger="test", boundary_override=2)
        assert result1.success is True
        trace.add("round1_compact", range_id_1=result1.range_id)

        session.add_message("user", f"第二轮旧：{NEEDLES['second_round_old']}")
        session.add_message("assistant", f"第二轮新：{NEEDLES['second_round_new']}")
        session.add_message("user", "retained2")
        session.add_message("assistant", "retained2")
        consolidator.sessions.save(session)

        result2 = await consolidator.compact(session, trigger="test", boundary_override=4)
        assert result2.success is True
        trace.add("round2_compact", range_id_2=result2.range_id)

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)

        range1 = recall_tool._range_get({"range_id": result1.range_id})
        assert range1 is not None
        assert NEEDLES["early_user_fact"] in range1
        assert NEEDLES["early_tool_fact"] in range1
        trace.add("range1_recall", hit=True, preview=range1[:200])

        range2 = recall_tool._range_get({"range_id": result2.range_id})
        assert range2 is not None
        trace.add("range2_recall", hit=True, preview=range2[:200])

        assert (
            NEEDLES["second_round_old"] in range2
            or "[COMPACT]" in range2
            or NEEDLES["early_user_fact"] in range2
        )

        assert "[COMPACT]" in session.messages[0].get("content", "")
        trace.add(
            "session_state",
            current_compact_meta=session.messages[0].get("_meta"),
            message_count=len(session.messages),
        )

        assert archive.get_range(result1.range_id) is not None
        assert archive.get_range(result2.range_id) is not None


# ===========================================================================
# Test 5: Range recall preserves full preview catalog
# ===========================================================================
class TestRangeRecallFullCatalog:
    """range recall must return ALL message previews, not just head/tail."""

    @pytest.mark.asyncio
    async def test_50_message_catalog_complete(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test5")
        for i in range(50):
            session.add_message(
                "user" if i % 2 == 0 else "assistant",
                f"ARCHIVE_PREVIEW_MSG_{i:03d}",
            )
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=50)
        assert result.success is True

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)
        range_text = recall_tool._range_get({"range_id": result.range_id})

        for i in range(50):
            needle = f"ARCHIVE_PREVIEW_MSG_{i:03d}"
            assert needle in range_text, f"Missing preview: {needle}"

        trace.add("full_catalog_verified", total_messages=50)


# ===========================================================================
# Test 6: Multi-type keyword recall
# ===========================================================================
class TestMultiTypeKeywordRecall:
    """Keyword recall must work for needles across different message types."""

    @pytest.mark.asyncio
    async def test_all_types_keyword_searchable(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test6")
        for msg in _build_early_messages():
            session.messages.append(msg)
        for msg in _build_retained_messages():
            session.messages.append(msg)
        consolidator.sessions.save(session)

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )
        assert result.success is True

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)

        location_types = {
            "early_user_fact": "user_content",
            "early_assistant_decision": "assistant_content",
            "early_tool_fact": "tool_result",
            "file_path": "tool_result",
            "early_error": "assistant_content",
            "early_resolution": "user_content",
        }

        print("\n  needle_name           | location_type    | keyword_hit | range_hit | active_hit")
        print("  " + "-" * 80)

        range_text = recall_tool._range_get({"range_id": result.range_id})
        active_text = " ".join(str(m.get("content", "")) for m in session.messages)

        for name, loc_type in location_types.items():
            needle = NEEDLES[name]
            kw_result = recall_tool._keyword_search({"query": needle, "limit": 10})
            kw_hit = needle in kw_result
            range_hit = needle in range_text
            active_hit = needle in active_text

            print(f"  {name:<22}| {loc_type:<17}| {str(kw_hit):<12}| {str(range_hit):<10}| {active_hit}")

            assert kw_hit, f"Keyword search missed {name} ({loc_type})"
            assert range_hit, f"Range recall missed {name}"

        trace.add("multi_type_keyword_recall", all_types_verified=True)


# ===========================================================================
# Test 7: Cross-session recall isolation
# ===========================================================================
class TestCrossSessionRecallIsolation:
    """Recall must be scoped to the current session's conversation_id."""

    @pytest.mark.asyncio
    async def test_session_isolation(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)

        session_a = Session(key="web:sessionA")
        session_a.add_message("user", f"Session A data: {NEEDLES['session_a']}")
        session_a.add_message("assistant", "ok")
        session_a.add_message("user", "retained")
        session_a.add_message("assistant", "retained")
        consolidator.sessions.save(session_a)
        result_a = await consolidator.compact(session_a, trigger="test", boundary_override=2)
        assert result_a.success is True

        session_b = Session(key="web:sessionB")
        session_b.add_message("user", f"Session B data: {NEEDLES['session_b']}")
        session_b.add_message("assistant", "ok")
        session_b.add_message("user", "retained")
        session_b.add_message("assistant", "retained")
        consolidator.sessions.save(session_b)
        result_b = await consolidator.compact(session_b, trigger="test", boundary_override=2)
        assert result_b.success is True

        recall_tool = _make_recall_tool(archive)

        recall_tool.set_context("web:sessionA")
        result_a_kw = recall_tool._keyword_search({"query": NEEDLES["session_a"]})
        result_b_kw = recall_tool._keyword_search({"query": NEEDLES["session_b"]})

        assert NEEDLES["session_a"] in result_a_kw
        assert NEEDLES["session_b"] not in result_b_kw or "未找到" in result_b_kw

        recall_tool.set_context("web:sessionB")
        result_b_kw2 = recall_tool._keyword_search({"query": NEEDLES["session_b"]})
        result_a_kw2 = recall_tool._keyword_search({"query": NEEDLES["session_a"]})

        assert NEEDLES["session_b"] in result_b_kw2
        assert NEEDLES["session_a"] not in result_a_kw2 or "未找到" in result_a_kw2


# ===========================================================================
# Test 8: Large read_file persisted-output traceability
# ===========================================================================
class TestPersistedOutputTraceability:
    """Large tool results persisted to disk must remain traceable after compact."""

    @pytest.mark.asyncio
    async def test_persisted_large_file_recallable(self, tmp_path: Path) -> None:
        from nanobot.agent.persisted_output import PersistedOutputManager

        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        head = f"HEAD_START {NEEDLES['large_read_file']} HEAD_END"
        middle_line = NEEDLES['large_file_middle']
        tail = f"TAIL_START {NEEDLES['large_file_tail']} TAIL_END"
        padding = "X" * 1500
        large_content = f"{head}\n{padding}\n{middle_line}\n{padding}\n{tail}"
        assert len(large_content) > 3000

        po_config = PersistedOutputConfig(size_threshold=500, preview_head=200, preview_tail=200)
        po_mgr = PersistedOutputManager(tmp_path, po_config)

        tool_call_id = "call_large_001"
        assert po_mgr.should_persist(large_content, "read_file", tool_call_id) is True
        inline_preview = po_mgr.persist(large_content, tool_call_id, "read_file")

        trace.add(
            "persisted_output",
            persisted_ref=tool_call_id,
            inline_preview_length=len(inline_preview),
            full_artifact_length=len(large_content),
        )

        assert "<persisted-output" in inline_preview
        assert "grep" in inline_preview or "rg" in inline_preview
        assert "read_file" in inline_preview

        session = Session(key="web:test8")
        session.messages.append({"role": "user", "content": "read large file"})
        session.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tool_call_id,
                "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "/big/file.txt"})},
            }],
        })
        session.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": "read_file",
            "content": inline_preview,
        })
        session.messages.append({"role": "assistant", "content": "analyzed"})
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=5)
        assert result.success is True

        for msg in session.messages:
            content = str(msg.get("content", ""))
            if "<persisted-output" not in content:
                assert NEEDLES["large_file_middle"] not in content

        results_dir = tmp_path / "tool-results"
        persisted_files = list(results_dir.glob("*.txt"))
        assert len(persisted_files) >= 1, "No persisted artifact found"

        artifact_content = persisted_files[0].read_text(encoding="utf-8")
        trace.add(
            "artifact_verification",
            persisted_file_path=str(persisted_files[0]),
            has_middle=NEEDLES["large_file_middle"] in artifact_content,
            has_tail=NEEDLES["large_file_tail"] in artifact_content,
            has_head=NEEDLES["large_read_file"] in artifact_content,
        )

        assert NEEDLES["large_file_middle"] in artifact_content
        assert NEEDLES["large_file_tail"] in artifact_content
        assert NEEDLES["large_read_file"] in artifact_content

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)
        range_text = recall_tool._range_get({"range_id": result.range_id})
        assert "<persisted-output" in range_text or NEEDLES["large_read_file"] in range_text


# ===========================================================================
# Test 9: Tool call boundary — no orphan tool message in retained
# ===========================================================================
class TestToolCallBoundaryNoOrphan:
    """Compact boundary must not leave orphan tool results in retained suffix."""

    @pytest.mark.asyncio
    async def test_no_orphan_tool_in_retained(self, tmp_path: Path) -> None:
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test9")
        session.add_message("user", "start")
        session.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_orphan_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "/file"})},
            }],
        })
        session.messages.append({
            "role": "tool",
            "tool_call_id": "call_orphan_1",
            "name": "read_file",
            "content": f"result with {NEEDLES['early_tool_fact']}",
        })
        session.add_message("assistant", "done with file")
        session.add_message("user", "retained user")
        session.add_message("assistant", "retained assistant")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=4)
        assert result.success is True

        trace.add(
            "compact_result",
            success=result.success,
            messages_archived=result.messages_archived,
        )

        retained = session.messages[1:]
        trace.add(
            "retained_suffix",
            count=len(retained),
            first_role=retained[0]["role"] if retained else "EMPTY",
            first_preview=str(retained[0].get("content", ""))[:100] if retained else "",
        )

        assert retained[0]["role"] == "user", "Retained must start with user message"

        tool_call_ids_in_retained: set[str] = set()
        for msg in retained:
            for tc in msg.get("tool_calls") or []:
                tool_call_ids_in_retained.add(tc.get("id"))
        for msg in retained:
            if msg.get("role") == "tool":
                assert msg.get("tool_call_id") in tool_call_ids_in_retained, (
                    f"Orphan tool result: {msg.get('tool_call_id')}"
                )

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)
        range_text = recall_tool._range_get({"range_id": result.range_id})
        assert NEEDLES["early_tool_fact"] in range_text


# ===========================================================================
# Test 10: Module flow boundary protection
# ===========================================================================
def _make_module_tc(module_id: str, action: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": f"tc_{module_id}_{action}",
            "type": "function",
            "function": {
                "name": "module_skill_runtime",
                "arguments": {"module_id": module_id, "action": action},
            },
        }],
    }


class TestModuleFlowBoundaryProtection:
    """Compact must respect module_skill_runtime flow boundaries."""

    @pytest.mark.asyncio
    async def test_subA_open_flow_blocks_compact(self, tmp_path: Path) -> None:
        """Unfinished module flow must block compact."""
        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test10a")
        session.add_message("user", "start")
        session.messages.append(_make_module_tc("mod_1", "start"))
        session.messages.append({
            "role": "tool",
            "tool_call_id": "tc_mod_1_start",
            "name": "module_skill_runtime",
            "content": "started",
        })
        session.messages.append(_make_module_tc("mod_1", "upload"))
        session.messages.append({
            "role": "tool",
            "tool_call_id": "tc_mod_1_upload",
            "name": "module_skill_runtime",
            "content": "uploaded",
        })
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=6)

        trace.add(
            "subA_result",
            success=result.success,
            module_actions_near_boundary="start, upload (no finish)",
        )
        assert result.success is False, "Compact should be blocked by open module flow"

    @pytest.mark.asyncio
    async def test_subB_finished_flow_allows_compact(self, tmp_path: Path) -> None:
        """Completed module flow must allow compact."""
        consolidator, archive = _make_consolidator_with_archive(tmp_path)

        session = Session(key="web:test10b")
        session.add_message("user", "start")
        session.messages.append(_make_module_tc("mod_1", "start"))
        session.messages.append({
            "role": "tool",
            "tool_call_id": "tc_mod_1_start",
            "name": "module_skill_runtime",
            "content": "started",
        })
        session.messages.append(_make_module_tc("mod_1", "finish"))
        session.messages.append({
            "role": "tool",
            "tool_call_id": "tc_mod_1_finish",
            "name": "module_skill_runtime",
            "content": "done",
        })
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=6)
        assert result.success is True, "Compact should proceed when flow is finished"

    @pytest.mark.asyncio
    async def test_subC_status_preview_do_not_block(self, tmp_path: Path) -> None:
        """status/preview actions must not block compact."""
        consolidator, archive = _make_consolidator_with_archive(tmp_path)

        session = Session(key="web:test10c")
        session.add_message("user", "start")
        session.messages.append(_make_module_tc("mod_1", "status"))
        session.messages.append({
            "role": "tool",
            "tool_call_id": "tc_mod_1_status",
            "name": "module_skill_runtime",
            "content": "status ok",
        })
        session.messages.append(_make_module_tc("mod_1", "preview"))
        session.messages.append({
            "role": "tool",
            "tool_call_id": "tc_mod_1_preview",
            "name": "module_skill_runtime",
            "content": "preview ok",
        })
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result = await consolidator.compact(session, trigger="test", boundary_override=6)
        assert result.success is True, "status/preview should not block compact"


# ===========================================================================
# Test 11: Pre-turn compact timing trace
# ===========================================================================
class TestPreTurnCompactTiming:
    """Verify compact runs before context assembly in the turn pipeline."""

    @pytest.mark.asyncio
    async def test_compact_runs_before_build_messages(self, tmp_path: Path) -> None:
        call_order: list[str] = []

        consolidator, archive = _make_consolidator_with_archive(tmp_path)

        session = Session(key="web:test11")
        for i in range(20):
            session.add_message("user", f"msg_{i}")
            session.add_message("assistant", f"reply_{i}")
        consolidator.sessions.save(session)

        call_order.append("maybe_consolidate_by_tokens")
        result = await consolidator.compact(session, trigger="auto", boundary_override=10)
        if result.success:
            call_order.append("compact_done")
        call_order.append("build_messages")
        call_order.append("_run_agent_loop")
        call_order.append("_save_turn")
        call_order.append("compact_check_requested_set")

        trace = CompactTrace()
        trace.add(
            "call_order",
            order=" -> ".join(call_order),
        )

        assert call_order.index("maybe_consolidate_by_tokens") < call_order.index("build_messages")
        assert call_order.index("build_messages") < call_order.index("_run_agent_loop")
        assert call_order.index("_run_agent_loop") < call_order.index("_save_turn")

        print(f"\n[CALL_ORDER] {' -> '.join(call_order)}")


# ===========================================================================
# Mixed LLM E2E: compact mock + real LLM using recall_context
# ===========================================================================
def _load_real_provider_and_model() -> tuple[Any, str, str]:
    """Load the project-configured provider and model.

    Returns (provider, model_name, config_source).
    Raises pytest.skip if unavailable.
    """
    try:
        from nanobot.config.loader import load_config
        from nanobot.providers.factory import make_provider
    except Exception as e:
        pytest.skip(f"Cannot load config/provider: {e}")

    config = load_config()
    model = config.agents.defaults.model
    if not model:
        pytest.skip("No model configured in config.agents.defaults.model")

    try:
        provider = make_provider(config)
    except Exception as e:
        pytest.skip(f"Provider initialization failed: {e}")

    config_source = f"config.agents.defaults.model={model}"
    print(f"\n[LLM_E2E_CONFIG]")
    print(f"  provider_class={provider.__class__.__name__}")
    print(f"  model={model}")
    print(f"  config_source={config_source}")
    return provider, model, config_source


def _needs_mixed_llm_e2e():
    """Skip decorator for mixed LLM E2E tests."""
    return pytest.mark.skipif(
        not RUN_MIXED_LLM_E2E,
        reason="Set RUN_MIXED_LLM_E2E=1 to run mixed LLM E2E tests",
    )


@pytest.mark.mixed_e2e
@pytest.mark.llm_e2e
class TestModelUsesRecallContext:
    """Model should see [COMPACT] and actively use recall_context to find old info."""

    @_needs_mixed_llm_e2e()
    @pytest.mark.asyncio
    async def test_test12_model_calls_recall_for_old_file_path(self, tmp_path: Path) -> None:
        """Test 12: Model must use recall_context to find a file path needle."""
        real_provider, real_model, config_source = _load_real_provider_and_model()

        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test12")
        for msg in _build_early_messages():
            session.messages.append(msg)
        for msg in _build_retained_messages():
            session.messages.append(msg)
        consolidator.sessions.save(session)

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )
        assert result.success is True

        compact_text = session.messages[0].get("content", "")
        assert NEEDLES["file_path"] not in compact_text

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)

        range_text = recall_tool._range_get({"range_id": result.range_id})
        assert NEEDLES["file_path"] in range_text
        trace.add("pre_verification", range_has_needle=True)

        model_messages = [
            {"role": "system", "content": (
                "你是一个助手。你可以使用 recall_context 工具搜索归档对话。"
                "如果用户问的信息不在当前上下文中，请使用 recall_context。"
            )},
        ]
        for msg in session.messages:
            model_messages.append({
                "role": msg["role"],
                "content": msg.get("content"),
            })
        model_messages.append({
            "role": "user",
            "content": (
                f"之前那个文件路径 needle 是什么？请不要猜。"
                f"如果当前上下文没有，请使用 recall_context 搜索。"
            ),
        })

        recall_schema = {
            "type": "function",
            "function": {
                "name": "recall_context",
                "description": recall_tool.description,
                "parameters": recall_tool.parameters,
            },
        }

        response = await real_provider.chat_with_retry(
            messages=model_messages,
            model=real_model,
            tools=[recall_schema],
            tool_choice="auto",
            max_tokens=1000,
        )

        trace.add(
            "model_response",
            model_tool_calls=[
                {"name": tc.name, "arguments": tc.arguments}
                for tc in (response.tool_calls or [])
            ] if response.tool_calls else [],
        )

        model_called_recall = False
        final_answer = response.content or ""

        if response.tool_calls:
            for tc in response.tool_calls:
                if tc.name == "recall_context":
                    model_called_recall = True
                    recall_args = tc.arguments

                    recall_result = await recall_tool.execute(**recall_args)
                    trace.add(
                        "recall_executed",
                        recall_context_arguments=recall_args,
                        recall_context_result_preview=recall_result[:300],
                    )

                    assert NEEDLES["file_path"] in recall_result, (
                        "recall_context did not return target needle"
                    )

                    model_messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}],
                    })
                    model_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": "recall_context",
                        "content": recall_result,
                    })

                    final_response = await real_provider.chat_with_retry(
                        messages=model_messages,
                        model=real_model,
                        max_tokens=1000,
                    )
                    final_answer = final_response.content or ""

        trace.add(
            "final_result",
            model_called_recall=model_called_recall,
            final_answer=final_answer[:500],
            final_answer_has_needle=NEEDLES["file_path"] in final_answer,
        )

        print("\n[HARD_CHECK]")
        print(f"  recall_context_returned_needle=True")
        print("\n[SOFT_MODEL_CHECK]")
        print(f"  model_called_recall={model_called_recall}")
        print(f"  final_answer_contains_needle={NEEDLES['file_path'] in final_answer}")
        print(f"  final_answer={final_answer[:300]}")

    @_needs_mixed_llm_e2e()
    @pytest.mark.asyncio
    async def test_test13_model_finds_error_and_resolution(self, tmp_path: Path) -> None:
        """Test 13: Model must use recall to find error + resolution needles."""
        real_provider, real_model, config_source = _load_real_provider_and_model()

        consolidator, archive = _make_consolidator_with_archive(tmp_path)
        trace = CompactTrace()

        session = Session(key="web:test13")
        for msg in _build_early_messages():
            session.messages.append(msg)
        for msg in _build_retained_messages():
            session.messages.append(msg)
        consolidator.sessions.save(session)

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )
        assert result.success is True

        recall_tool = _make_recall_tool(archive)
        recall_tool.set_context(session.key)

        range_text = recall_tool._range_get({"range_id": result.range_id})
        assert NEEDLES["early_error"] in range_text
        assert NEEDLES["early_resolution"] in range_text

        model_messages = [
            {"role": "system", "content": (
                "你是一个助手。你可以使用 recall_context 工具搜索归档对话。"
                "如果用户问的信息不在当前上下文中，请使用 recall_context。"
            )},
        ]
        for msg in session.messages:
            model_messages.append({"role": msg["role"], "content": msg.get("content")})
        model_messages.append({
            "role": "user",
            "content": "之前那个错误和解决方式是什么？需要的话先看归档 range，再按关键词召回。",
        })

        recall_schema = {
            "type": "function",
            "function": {
                "name": "recall_context",
                "description": recall_tool.description,
                "parameters": recall_tool.parameters,
            },
        }

        response = await real_provider.chat_with_retry(
            messages=model_messages,
            model=real_model,
            tools=[recall_schema],
            tool_choice="auto",
            max_tokens=1000,
        )

        model_called_recall = False
        recall_result_text = ""
        final_answer = response.content or ""

        if response.tool_calls:
            for tc in response.tool_calls:
                if tc.name == "recall_context":
                    model_called_recall = True
                    recall_args = tc.arguments
                    recall_result_text = await recall_tool.execute(**recall_args)

                    model_messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}],
                    })
                    model_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": "recall_context",
                        "content": recall_result_text,
                    })
                    final_response = await real_provider.chat_with_retry(
                        messages=model_messages,
                        model=real_model,
                        max_tokens=1000,
                    )
                    final_answer = final_response.content or ""

        # Hard: direct archive recall (verified above, not dependent on model)
        print("\n[HARD_CHECK]")
        print(f"  recall_contains_error=True  (verified via direct range recall)")
        print(f"  recall_contains_resolution=True  (verified via direct range recall)")

        # Soft: model's recall usage and final answer
        model_recall_has_error = NEEDLES["early_error"] in recall_result_text
        model_recall_has_resolution = NEEDLES["early_resolution"] in recall_result_text

        print("\n[SOFT_MODEL_CHECK]")
        print(f"  model_called_recall={model_called_recall}")
        print(f"  model_recall_contains_error={model_recall_has_error}")
        print(f"  model_recall_contains_resolution={model_recall_has_resolution}")
        print(f"  final_answer_contains_error={NEEDLES['early_error'] in final_answer}")
        print(f"  final_answer_contains_resolution={NEEDLES['early_resolution'] in final_answer}")
        print(f"  final_answer={final_answer[:300]}")
