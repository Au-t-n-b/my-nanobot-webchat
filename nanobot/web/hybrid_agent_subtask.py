"""Controlled Agent subtask for Skill-First hybrid mode (bounded tool loop)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.skills import BUILTIN_SKILLS_DIR
from nanobot.agent.tools.doc_text import ExtractDocTextTool
from nanobot.agent.tools.filesystem import (
    ListDirTool,
    ReadFileHeadTool,
    ReadFileTailTool,
    ReadFileTool,
    ReadHexDumpTool,
)
from nanobot.web.file_insight_report import FileInsightReport, parse_file_insight_report_from_llm_text
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.utils.helpers import build_assistant_message

_INLINE_MAX = 2000


def _truncate_content(result: Any, max_chars: int = _INLINE_MAX) -> str:
    if isinstance(result, str):
        text = result
    else:
        try:
            text = json.dumps(result, ensure_ascii=False)
        except Exception:
            text = str(result)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24] + "\n…(truncated)"


def _build_tool_registry(
    *,
    workspace: Path,
    restrict_to_workspace: bool,
    allowed_tool_names: list[str],
) -> ToolRegistry:
    allowed = {str(n).strip().lower() for n in allowed_tool_names if str(n).strip()}
    tools = ToolRegistry()
    allowed_dir = workspace if restrict_to_workspace else None
    extra_read = [BUILTIN_SKILLS_DIR] if allowed_dir else None
    if "read_file" in allowed:
        tools.register(
            ReadFileTool(workspace=workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read)
        )
    if "read_file_head" in allowed:
        tools.register(
            ReadFileHeadTool(workspace=workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read)
        )
    if "read_file_tail" in allowed:
        tools.register(
            ReadFileTailTool(workspace=workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read)
        )
    if "read_hex_dump" in allowed:
        tools.register(
            ReadHexDumpTool(workspace=workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read)
        )
    if "list_dir" in allowed:
        tools.register(ListDirTool(workspace=workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read))
    if "extract_doc_text" in allowed:
        # Always enforce workspace restriction at the tool level.
        tools.register(ExtractDocTextTool(workspace=workspace))
    return tools


def _file_insight_system_prompt(*, workspace: Path) -> str:
    schema = FileInsightReport.model_json_schema()
    schema_hint = json.dumps(schema, ensure_ascii=False)[:4000]
    return (
        "你是文件预览「洞察」子任务中的受控分析助手。\n"
        "规则：\n"
        "1) 只使用被提供的工具获取事实，不得编造文件内容。\n"
        "2) 最终回复必须是 **单行合法 JSON 对象**（不要 markdown、不要 ``` 围栏、不要前后解释文字）。\n"
        "3) JSON 必须严格满足以下 JSON Schema 的字段与枚举：\n"
        f"{schema_hint}\n"
        "4) extracted_snippets 最多 20 条，每条建议不超过 400 字符。\n"
        "5) 若信息不足，仍输出合法 JSON，在 summary 中说明缺什么，risk_level 可标为 warning。\n"
        f"\n## 工作区根路径\n{workspace}\n"
    )


async def run_hybrid_agent_subtask(
    *,
    agent_loop: Any,
    goal: str,
    allowed_tools: list[str],
    max_iterations: int = 8,
    output_mode: str = "summary_zh",
) -> dict[str, Any]:
    """Run a small tool-using loop; returns ``{ok, text, error?, report?}``."""
    if agent_loop is None:
        return {"ok": False, "error": "no_agent_loop", "text": ""}
    provider = getattr(agent_loop, "provider", None)
    if provider is None:
        return {"ok": False, "error": "no_provider", "text": ""}

    workspace: Path = getattr(agent_loop, "workspace", None) or Path(".").resolve()
    model = getattr(agent_loop, "model", None)
    if not model:
        model = provider.get_default_model()

    # Hybrid subtasks: always sandbox filesystem tools to agent workspace (do not inherit global default).
    tools = _build_tool_registry(
        workspace=workspace,
        restrict_to_workspace=True,
        allowed_tool_names=allowed_tools,
    )
    defs = tools.get_definitions()
    if not defs:
        return {"ok": False, "error": "no_tools_allowed", "text": ""}

    mode = str(output_mode or "summary_zh").strip().lower()
    if mode == "file_insight_json":
        system_prompt = _file_insight_system_prompt(workspace=workspace)
    else:
        system_prompt = (
            "你是嵌在工勘 Skill 流程内的受控分析助手。\n"
            "规则：\n"
            "1) 只使用被提供的工具获取事实，不得编造文件内容。\n"
            "2) 最终只输出一段简洁中文结论（建议不超过 400 字），不要输出 JSON 包裹。\n"
            "3) 若信息不足，明确说明缺什么，仍保持简短。\n"
            f"\n## 工作区根路径\n{workspace}\n"
        )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": goal},
    ]

    iteration = 0
    final_text: str | None = None
    try:
        while iteration < max(1, int(max_iterations)):
            iteration += 1
            response = await provider.chat_with_retry(
                messages=messages,
                tools=defs,
                model=model,
            )
            if response.has_tool_calls:
                tool_call_dicts = [tc.to_openai_tool_call() for tc in response.tool_calls]
                messages.append(
                    build_assistant_message(
                        response.content or "",
                        tool_calls=tool_call_dicts,
                        reasoning_content=response.reasoning_content,
                        thinking_blocks=response.thinking_blocks,
                    )
                )
                for tool_call in response.tool_calls:
                    raw = await tools.execute(
                        tool_call.name,
                        tool_call.arguments,
                        _nanobot_tool_call_id=tool_call.id,
                    )
                    content = _truncate_content(raw)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": content,
                        }
                    )
            else:
                final_text = (response.content or "").strip()
                break

        if final_text is None:
            final_text = (
                '{"file_type_guess":"unknown","summary":"在迭代上限内未得到模型最终输出",'
                '"risk_level":"warning","extracted_snippets":[],"next_action_suggestion":"重试或缩小文件"}'
                if mode == "file_insight_json"
                else "子任务结束：在迭代上限内未得到最终自然语言结论。"
            )
        if mode == "file_insight_json":
            try:
                report = parse_file_insight_report_from_llm_text(final_text)
                return {"ok": True, "text": final_text, "report": report.model_dump(mode="json")}
            except Exception as e:
                logger.warning("hybrid_agent_subtask file_insight_json parse failed | {}", e)
                return {
                    "ok": False,
                    "error": f"invalid_file_insight_json: {e}",
                    "text": (final_text or "")[:4000],
                }
        return {"ok": True, "text": final_text}
    except Exception as e:
        logger.warning("hybrid_agent_subtask failed | {}", e)
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "text": ""}
