"""Full LLM E2E tests for compact/archive/recall.

All tests use the project-configured real LLM for:
- Compact summary generation (real _generate_leaf)
- Agent recall usage
- recall_context with real tool chain

Default: skipped. Enable with RUN_LLM_E2E=1.
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
from nanobot.config.schema import ConsolidationConfig, MessageArchiveConfig
from nanobot.providers.base import GenerationSettings, LLMResponse
from nanobot.session.manager import Session, SessionManager

# ---------------------------------------------------------------------------
# Environment gates
# ---------------------------------------------------------------------------
TRACE_ENABLED = os.getenv("COMPACT_TRACE", "1") != "0"
RUN_LLM_E2E = os.getenv("RUN_LLM_E2E", "0") == "1"

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
}


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


def _load_real_provider_and_model():
    """Load project-configured provider and model. pytest.skip if unavailable."""
    try:
        from nanobot.config.loader import load_config
        from nanobot.providers.factory import make_provider
    except Exception as e:
        pytest.skip(f"Cannot load config/provider: {e}")

    config = load_config()
    model = config.agents.defaults.model
    if not model:
        pytest.skip("No model configured")

    try:
        provider = make_provider(config)
    except Exception as e:
        pytest.skip(f"Provider init failed: {e}")

    print(f"\n[LLM_E2E_CONFIG]")
    print(f"  provider_class={provider.__class__.__name__}")
    print(f"  model={model}")
    return provider, model


def _make_real_consolidator(tmp_path: Path, provider: Any, model: str) -> tuple[MemoryConsolidator, MessageArchive]:
    """Build consolidator with REAL provider for _generate_leaf."""
    cfg = ConsolidationConfig()
    sessions = SessionManager(tmp_path)
    archive = MessageArchive(tmp_path, MessageArchiveConfig())

    consolidator = MemoryConsolidator(
        workspace=tmp_path,
        provider=provider,
        model=model,
        sessions=sessions,
        context_window_tokens=65536,
        build_messages=lambda **kw: [],
        get_tool_definitions=lambda: [],
        consolidation_config=cfg,
    )
    consolidator.wire_subsystems(archive=archive)
    return consolidator, archive


def _build_early_messages() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": f"用户需求：{NEEDLES['early_user_fact']}"},
        {"role": "assistant", "content": f"关键决策：{NEEDLES['early_assistant_decision']}"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_read_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "/some/file.py"})},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call_read_1",
            "name": "read_file",
            "content": f"文件输出包含 {NEEDLES['early_tool_fact']}\n文件路径 {NEEDLES['file_path']}",
        },
        {"role": "assistant", "content": f"发现错误：{NEEDLES['early_error']}"},
        {"role": "user", "content": f"解决偏好：{NEEDLES['early_resolution']}"},
        {"role": "assistant", "content": "已解决。"},
    ]


skip_unless_llm_e2e = pytest.mark.skipif(
    not RUN_LLM_E2E,
    reason="Set RUN_LLM_E2E=1 to run full LLM E2E tests",
)


@pytest.mark.llm_e2e
@pytest.mark.slow
class TestRealCompactRealRecall:
    """Test 14: Real LLM compact + real recall, verify information recovery."""

    @skip_unless_llm_e2e
    @pytest.mark.asyncio
    async def test_test14_real_compact_recall_finds_needles(self, tmp_path: Path) -> None:
        provider, model = _load_real_provider_and_model()
        consolidator, archive = _make_real_consolidator(tmp_path, provider, model)
        trace = CompactTrace()

        session = Session(key="web:test14")
        for msg in _build_early_messages():
            session.messages.append(msg)
        session.add_message("user", f"最近：{NEEDLES['retained_recent']}")
        session.add_message("assistant", "继续")
        consolidator.sessions.save(session)

        trace.add("before_compact", message_count=len(session.messages))

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )
        assert result.success is True
        trace.add(
            "real_compact_done",
            range_id=result.range_id,
            messages_archived=result.messages_archived,
            summary_preview=result.summary_preview[:300] if result.summary_preview else "",
        )

        recall_tool = RecallContextTool(archive)
        recall_tool.set_context(session.key)

        range_text = recall_tool._range_get({"range_id": result.range_id})
        rows = archive._conn.execute(
            "SELECT content FROM archived_messages WHERE range_id = ?",
            (result.range_id,),
        ).fetchall()
        archive_raw = " ".join(str(r[0]) or "" for r in rows)

        target_needles = ["early_user_fact", "early_tool_fact", "early_assistant_decision", "file_path"]

        print("\n[HARD_CHECK]")
        for name in target_needles:
            in_range = NEEDLES[name] in range_text
            in_archive = NEEDLES[name] in archive_raw
            print(f"  {name}: range_recall={in_range}, archive_raw={in_archive}")
            assert in_range, f"{name} missing from range recall"
            assert in_archive, f"{name} missing from archive raw"

        for name in target_needles:
            kw_result = recall_tool._keyword_search({"query": NEEDLES[name]})
            assert NEEDLES[name] in kw_result, f"{name} missing from keyword recall"

        model_messages = [
            {"role": "system", "content": "你是一个助手。你可以使用 recall_context 工具搜索归档对话。"},
        ]
        for msg in session.messages:
            model_messages.append({"role": msg["role"], "content": msg.get("content")})
        model_messages.append({
            "role": "user",
            "content": "请找回之前那个文件路径 needle。如果当前上下文没有，请使用 recall_context。",
        })

        recall_schema = {
            "type": "function",
            "function": {
                "name": "recall_context",
                "description": recall_tool.description,
                "parameters": recall_tool.parameters,
            },
        }

        response = await provider.chat_with_retry(
            messages=model_messages, model=model,
            tools=[recall_schema], tool_choice="auto", max_tokens=1000,
        )

        model_called_recall = False
        final_answer = response.content or ""
        if response.tool_calls:
            for tc in response.tool_calls:
                if tc.name == "recall_context":
                    model_called_recall = True
                    recall_args = tc.arguments
                    recall_result = await recall_tool.execute(**recall_args)
                    model_messages.append({"role": "assistant", "content": response.content, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}]})
                    model_messages.append({"role": "tool", "tool_call_id": tc.id, "name": "recall_context", "content": recall_result})
                    final_response = await provider.chat_with_retry(messages=model_messages, model=model, max_tokens=1000)
                    final_answer = final_response.content or ""

        print("\n[SOFT_MODEL_CHECK]")
        print(f"  model_called_recall={model_called_recall}")
        print(f"  final_answer_contains_needle={NEEDLES['file_path'] in final_answer}")
        print(f"  final_answer={final_answer[:300]}")

    @skip_unless_llm_e2e
    @pytest.mark.asyncio
    async def test_test15_double_real_compact_both_ranges(self, tmp_path: Path) -> None:
        """Test 15: Two real compacts, both ranges recallable."""
        provider, model = _load_real_provider_and_model()
        consolidator, archive = _make_real_consolidator(tmp_path, provider, model)
        trace = CompactTrace()

        session = Session(key="web:test15")
        session.add_message("user", f"R1: {NEEDLES['early_user_fact']}")
        session.add_message("assistant", f"R1: {NEEDLES['early_tool_fact']}")
        session.add_message("user", "retained")
        session.add_message("assistant", "retained")
        consolidator.sessions.save(session)

        result1 = await consolidator.compact(session, trigger="test", boundary_override=2)
        assert result1.success is True
        trace.add("round1", range_id_1=result1.range_id)

        session.add_message("user", f"R2: {NEEDLES['second_round_old']}")
        session.add_message("assistant", f"R2: {NEEDLES['second_round_new']}")
        session.add_message("user", "retained2")
        session.add_message("assistant", "retained2")
        consolidator.sessions.save(session)

        result2 = await consolidator.compact(session, trigger="test", boundary_override=4)
        assert result2.success is True
        trace.add("round2", range_id_2=result2.range_id)

        recall_tool = RecallContextTool(archive)
        recall_tool.set_context(session.key)

        r1 = recall_tool._range_get({"range_id": result1.range_id})
        r2 = recall_tool._range_get({"range_id": result2.range_id})
        assert r1 is not None, "range_id_1 not found"
        assert r2 is not None, "range_id_2 not found"

        assert NEEDLES["early_user_fact"] in r1
        assert NEEDLES["early_tool_fact"] in r1

        trace.add("both_ranges_recallable", r1_has_r1_needles=True, r2_has_r2_or_compact=(
            NEEDLES["second_round_old"] in r2 or "[COMPACT]" in r2
        ))

        model_messages = [
            {"role": "system", "content": "你是一个助手。你可以使用 recall_context 工具搜索归档对话。"},
        ]
        for msg in session.messages:
            model_messages.append({"role": msg["role"], "content": msg.get("content")})
        model_messages.append({
            "role": "user",
            "content": f"请找回第一轮中出现的 {NEEDLES['early_tool_fact']}。如果当前上下文没有，请使用 recall_context。",
        })

        recall_schema = {
            "type": "function",
            "function": {"name": "recall_context", "description": recall_tool.description, "parameters": recall_tool.parameters},
        }
        response = await provider.chat_with_retry(
            messages=model_messages, model=model,
            tools=[recall_schema], tool_choice="auto", max_tokens=1000,
        )

        model_called_recall = False
        final_answer = response.content or ""
        if response.tool_calls:
            for tc in response.tool_calls:
                if tc.name == "recall_context":
                    model_called_recall = True
                    recall_args = tc.arguments
                    recall_result = await recall_tool.execute(**recall_args)
                    model_messages.append({"role": "assistant", "content": response.content, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}]})
                    model_messages.append({"role": "tool", "tool_call_id": tc.id, "name": "recall_context", "content": recall_result})
                    final_response = await provider.chat_with_retry(messages=model_messages, model=model, max_tokens=1000)
                    final_answer = final_response.content or ""

        print(f"\n[SOFT_MODEL_CHECK]")
        print(f"  model_called_recall={model_called_recall}")
        print(f"  final_answer_contains_needle={NEEDLES['early_tool_fact'] in final_answer}")

    @skip_unless_llm_e2e
    @pytest.mark.asyncio
    async def test_test16_lossy_real_summary_recall_finds_details(self, tmp_path: Path) -> None:
        """Test 16: Real compact summary may be lossy, but recall finds details."""
        provider, model = _load_real_provider_and_model()
        consolidator, archive = _make_real_consolidator(tmp_path, provider, model)
        trace = CompactTrace()

        session = Session(key="web:test16")
        for msg in _build_early_messages():
            session.messages.append(msg)
        session.add_message("user", f"最近：{NEEDLES['retained_recent']}")
        session.add_message("assistant", "继续")
        consolidator.sessions.save(session)

        result = await consolidator.compact(
            session, trigger="test", boundary_override=len(_build_early_messages())
        )
        assert result.success is True

        compact_text = session.messages[0].get("content", "")
        summary_has_error = NEEDLES["early_error"] in compact_text
        trace.add("summary_contains_error", value=summary_has_error)

        recall_tool = RecallContextTool(archive)
        recall_tool.set_context(session.key)

        range_text = recall_tool._range_get({"range_id": result.range_id})
        kw_result = recall_tool._keyword_search({"query": NEEDLES["early_error"]})

        print("\n[HARD_CHECK]")
        print(f"  range_recall_contains_error={NEEDLES['early_error'] in range_text}")
        print(f"  keyword_recall_contains_error={NEEDLES['early_error'] in kw_result}")

        assert NEEDLES["early_error"] in range_text
        assert NEEDLES["early_error"] in kw_result

        model_messages = [
            {"role": "system", "content": "你是一个助手。你可以使用 recall_context 工具搜索归档对话。"},
        ]
        for msg in session.messages:
            model_messages.append({"role": msg["role"], "content": msg.get("content")})
        model_messages.append({
            "role": "user",
            "content": "早期错误 needle 是什么？请基于 recall_context，不要猜。",
        })

        recall_schema = {
            "type": "function",
            "function": {"name": "recall_context", "description": recall_tool.description, "parameters": recall_tool.parameters},
        }
        response = await provider.chat_with_retry(
            messages=model_messages, model=model,
            tools=[recall_schema], tool_choice="auto", max_tokens=1000,
        )

        model_called_recall = False
        final_answer = response.content or ""
        if response.tool_calls:
            for tc in response.tool_calls:
                if tc.name == "recall_context":
                    model_called_recall = True
                    recall_args = tc.arguments
                    recall_result = await recall_tool.execute(**recall_args)
                    model_messages.append({"role": "assistant", "content": response.content, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}]})
                    model_messages.append({"role": "tool", "tool_call_id": tc.id, "name": "recall_context", "content": recall_result})
                    final_response = await provider.chat_with_retry(messages=model_messages, model=model, max_tokens=1000)
                    final_answer = final_response.content or ""

        print("\n[SOFT_MODEL_CHECK]")
        print(f"  model_called_recall={model_called_recall}")
        print(f"  final_answer_contains_needle={NEEDLES['early_error'] in final_answer}")
        print(f"  final_answer={final_answer[:300]}")
