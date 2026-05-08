"""Session memory extractor: single-file summary.md per session (Claude Code style)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.schema import SessionMemoryConfig
from nanobot.utils.helpers import ensure_dir

_SM_SYSTEM_PROMPT = (
    "你是一个对话状态追踪代理。基于当前摘要和最新对话，输出更新后的完整摘要。"
)

_SM_USER_TEMPLATE = """## 当前摘要
{current_summary}

## 最近的新消息
{new_messages_text}

## 任务
将新消息的关键信息合并到摘要中，输出更新后的完整摘要。

## 输出格式（固定 sections，必须全部包含）
## Current State
当前进行到哪一步，还有哪些未完成的任务。2-3 句。
## Key Decisions
关键决策及理由。每条一行。
## Files
涉及的文件路径及状态。
## Errors & Resolutions
遇到的错误及解决方式。
## Worklog
按时间排列的操作日志。"""


def _format_messages_compact(messages: list[dict[str, Any]]) -> str:
    """Format messages for the SM prompt, truncating large tool outputs."""
    import json as _json

    lines: list[str] = []
    for msg in messages:
        ts = msg.get("timestamp", "?")
        if isinstance(ts, str) and len(ts) > 16:
            ts = ts[:16]
        role = msg.get("role", "?")
        content = msg.get("content", "")

        if isinstance(content, list):
            # multimodal content — extract text parts
            text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            content = " ".join(text_parts)

        if role == "user":
            text = str(content)[:500]
            lines.append(f"[{ts}] USER: {text}")
        elif role == "assistant":
            preview = str(content)[:200] if content else "(tool calls)"
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                summaries = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "?")
                    args_str = _json.dumps(fn.get("arguments", {}), ensure_ascii=False)[:80]
                    summaries.append(f"{name}({args_str})")
                preview += f" [{', '.join(summaries)}]"
            lines.append(f"[{ts}] ASSISTANT: {preview}")
        elif role == "tool":
            c = str(content)
            if "<persisted-output" in c:
                lines.append(f"[{ts}] TOOL [{msg.get('name', '?')}]: <persisted-output ref>")
            elif len(c) > 500:
                lines.append(f"[{ts}] TOOL [{msg.get('name', '?')}]: {c[:200]}...({len(c)} chars)")
            else:
                lines.append(f"[{ts}] TOOL [{msg.get('name', '?')}]: {c}")
    return "\n".join(lines)


class SessionMemoryExtractor:
    """Manages per-session summary.md files with background LLM extraction."""

    def __init__(self, workspace: Path, config: SessionMemoryConfig | None = None):
        self.config = config or SessionMemoryConfig()
        self.base_dir = ensure_dir(workspace / self.config.memory_dir)

    def _summary_path(self, session_key: str) -> Path:
        safe_key = session_key.replace(":", "_").replace("/", "_")
        return ensure_dir(self.base_dir / safe_key) / "summary.md"

    def read_summary(self, session_key: str) -> str | None:
        path = self._summary_path(session_key)
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            return content if content else None
        return None

    def _atomic_write(self, path: Path, content: str) -> None:
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(path))

    async def extract_incremental(
        self,
        session_key: str,
        messages_snapshot: list[dict[str, Any]],
        provider: Any = None,
        model: str | None = None,
    ) -> None:
        """Run LLM extraction to update summary.md. Called from background task."""
        if not provider:
            logger.debug("SM extraction skipped: no provider")
            return

        current = self.read_summary(session_key) or "(new session)"
        new_text = _format_messages_compact(messages_snapshot)

        prompt = _SM_USER_TEMPLATE.format(
            current_summary=current,
            new_messages_text=new_text,
        )

        try:
            response = await provider.chat_with_retry(
                messages=[
                    {"role": "system", "content": _SM_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=model or "deepseek/deepseek-chat",
                max_tokens=2000,
            )
            if response.content:
                path = self._summary_path(session_key)
                self._atomic_write(path, response.content.strip())
                logger.debug("SM extraction updated: {} ({} chars)", session_key, len(response.content))
        except Exception:
            logger.exception("SM extraction failed for {}", session_key)
