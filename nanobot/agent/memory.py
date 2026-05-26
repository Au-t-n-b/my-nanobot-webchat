"""Memory system for persistent agent memory."""

from __future__ import annotations

import asyncio
import copy
import json
import weakref
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from nanobot.utils.helpers import ensure_dir, estimate_message_tokens, estimate_prompt_tokens_chain

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session, SessionManager


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


def _ensure_text(value: Any) -> str:
    """Normalize tool-call payload values to text for file storage."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _normalize_save_memory_args(args: Any) -> dict[str, Any] | None:
    """Normalize provider tool-call arguments to the expected dict shape."""
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(args, list):
        return args[0] if args and isinstance(args[0], dict) else None
    return args if isinstance(args, dict) else None

_TOOL_CHOICE_ERROR_MARKERS = (
    "tool_choice",
    "toolchoice",
    "does not support",
    'should be ["none", "auto"]',
)


def _is_tool_choice_unsupported(content: str | None) -> bool:
    """Detect provider errors caused by forced tool_choice being unsupported."""
    text = (content or "").lower()
    return any(m in text for m in _TOOL_CHOICE_ERROR_MARKERS)


@dataclass
class CompactResult:
    """Result of a compact() call — carries statistics for the caller to display."""

    success: bool
    messages_archived: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    summary_preview: str = ""
    range_id: int | None = None


class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log)."""

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3

    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self._consecutive_failures = 0

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    async def consolidate(
        self,
        messages: list[dict],
        provider: LLMProvider,
        model: str,
    ) -> bool:
        """Consolidate the provided message chunk into MEMORY.md + HISTORY.md."""
        if not messages:
            return True

        current_memory = self.read_long_term()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{self._format_messages(messages)}"""

        chat_messages = [
            {"role": "system", "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation."},
            {"role": "user", "content": prompt},
        ]

        try:
            forced = {"type": "function", "function": {"name": "save_memory"}}
            response = await provider.chat_with_retry(
                messages=chat_messages,
                tools=_SAVE_MEMORY_TOOL,
                model=model,
                tool_choice=forced,
            )

            if response.finish_reason == "error" and _is_tool_choice_unsupported(
                response.content
            ):
                logger.warning("Forced tool_choice unsupported, retrying with auto")
                response = await provider.chat_with_retry(
                    messages=chat_messages,
                    tools=_SAVE_MEMORY_TOOL,
                    model=model,
                    tool_choice="auto",
                )

            if not response.has_tool_calls:
                logger.warning(
                    "Memory consolidation: LLM did not call save_memory "
                    "(finish_reason={}, content_len={}, content_preview={})",
                    response.finish_reason,
                    len(response.content or ""),
                    (response.content or "")[:200],
                )
                return self._fail_or_raw_archive(messages)

            args = _normalize_save_memory_args(response.tool_calls[0].arguments)
            if args is None:
                logger.warning("Memory consolidation: unexpected save_memory arguments")
                return self._fail_or_raw_archive(messages)

            if "history_entry" not in args or "memory_update" not in args:
                logger.warning("Memory consolidation: save_memory payload missing required fields")
                return self._fail_or_raw_archive(messages)

            entry = args["history_entry"]
            update = args["memory_update"]

            if entry is None or update is None:
                logger.warning("Memory consolidation: save_memory payload contains null required fields")
                return self._fail_or_raw_archive(messages)

            entry = _ensure_text(entry).strip()
            if not entry:
                logger.warning("Memory consolidation: history_entry is empty after normalization")
                return self._fail_or_raw_archive(messages)

            self.append_history(entry)
            update = _ensure_text(update)
            if update != current_memory:
                self.write_long_term(update)

            self._consecutive_failures = 0
            logger.info("Memory consolidation done for {} messages", len(messages))
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return self._fail_or_raw_archive(messages)

    def _fail_or_raw_archive(self, messages: list[dict]) -> bool:
        """Increment failure count; after threshold, raw-archive messages and return True."""
        self._consecutive_failures += 1
        if self._consecutive_failures < self._MAX_FAILURES_BEFORE_RAW_ARCHIVE:
            return False
        self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    def _raw_archive(self, messages: list[dict]) -> None:
        """Fallback: dump raw messages to HISTORY.md without LLM summarization."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.append_history(
            f"[{ts}] [RAW] {len(messages)} messages\n"
            f"{self._format_messages(messages)}"
        )
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages", len(messages)
        )


class MemoryConsolidator:
    """Owns consolidation policy, locking, and session offset updates."""

    _MAX_CONSOLIDATION_ROUNDS = 5

    _SAFETY_BUFFER = 1024  # extra headroom for tokenizer estimation drift

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        max_completion_tokens: int = 4096,
        consolidation_config: "ConsolidationConfig | None" = None,
    ):
        self.store = MemoryStore(workspace)
        self.provider = provider
        self.model = model
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._consecutive_failures = 0
        # Lazy import to avoid circular dependency
        if consolidation_config is None:
            from nanobot.config.schema import ConsolidationConfig
            consolidation_config = ConsolidationConfig()
        self._consolidation_config = consolidation_config
        # New subsystems — wired during AgentLoop integration (Step 6)
        self.archive: Any | None = None
        self.hook_runner: Any | None = None
        self.session_memory: Any | None = None

    def wire_subsystems(
        self,
        archive: Any | None = None,
        hook_runner: Any | None = None,
        session_memory: Any | None = None,
    ) -> None:
        """Wire new subsystems (called from AgentLoop integration)."""
        if archive is not None:
            self.archive = archive
        if hook_runner is not None:
            self.hook_runner = hook_runner
        if session_memory is not None:
            self.session_memory = session_memory

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    async def consolidate_messages(self, messages: list[dict[str, object]]) -> bool:
        """Archive a selected message chunk into persistent memory."""
        return await self.store.consolidate(messages, self.provider, self.model)

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """Pick a user-turn boundary that removes enough old prompt tokens."""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            removed_tokens += estimate_message_tokens(message)

        return last_boundary

    def estimate_session_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size for the normal session history view."""
        history = session.get_history(max_messages=None)
        channel, chat_id = (session.key.split(":", 1) if ":" in session.key else (None, None))
        probe_messages = self._build_messages(
            history=history,
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
        )
        return estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )

    async def archive_messages(self, messages: list[dict[str, object]]) -> bool:
        """Archive messages with guaranteed persistence (retries until raw-dump fallback)."""
        if not messages:
            return True
        for _ in range(self.store._MAX_FAILURES_BEFORE_RAW_ARCHIVE):
            if await self.consolidate_messages(messages):
                return True
        return True

    # ------------------------------------------------------------------
    # Unified compact() — replaces old consolidate() for token-based compaction
    # ------------------------------------------------------------------

    _LEAF_SYSTEM_PROMPT = (
        "你是一个对话压缩代理。将以下对话压缩为结构化摘要。"
        "严格按指定 sections 输出，不要添加额外内容。"
    )

    _LEAF_USER_TEMPLATE = """请将以下 {n} 条对话消息压缩为结构化摘要。
{extra_instructions}

## 对话内容
{conversation_text}

## 输出格式（固定 sections，必须全部包含）
## Current State
当前进行到哪一步，还有哪些未完成的任务。2-3 句。

## Key Decisions
关键决策及理由。每条一行：- 决策内容 → 理由。

## Files
涉及的文件路径及状态（创建/修改/读取/删除）。每条一行。

## Errors & Resolutions
遇到的错误及解决方式。每条一行。如无错误写「无」。

## Worklog
按时间排列的操作日志。每行格式：
[HH:MM] 工具名(参数摘要) → 结果摘要
包含每个工具调用，不遗漏。"""

    @staticmethod
    def _format_messages_compact(messages: list[dict[str, Any]]) -> str:
        """Format messages for leaf prompt, truncating large tool outputs."""
        lines: list[str] = []
        for msg in messages:
            ts = msg.get("timestamp", "?")
            if isinstance(ts, str) and len(ts) > 16:
                ts = ts[:16]
            role = msg.get("role", "?")
            content = msg.get("content", "")

            if isinstance(content, list):
                text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                content = " ".join(text_parts)

            if role == "user":
                lines.append(f"[{ts}] USER: {str(content)[:500]}")
            elif role == "assistant":
                preview = str(content)[:200] if content else "(tool calls)"
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    summaries = []
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "?")
                        args_str = json.dumps(fn.get("arguments", {}), ensure_ascii=False)[:80]
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

    async def _generate_leaf(
        self,
        chunk: list[dict[str, Any]],
        extra_instructions: str = "",
    ) -> str:
        """Call LLM to generate a structured leaf summary."""
        conv_text = self._format_messages_compact(chunk)
        prompt = self._LEAF_USER_TEMPLATE.format(
            n=len(chunk),
            extra_instructions=f"\n{extra_instructions}" if extra_instructions else "",
            conversation_text=conv_text,
        )
        try:
            response = await self.provider.chat_with_retry(
                messages=[
                    {"role": "system", "content": self._LEAF_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                max_tokens=2000,
            )
            return response.content.strip() if response.content else "(leaf generation failed)"
        except Exception:
            logger.exception("Leaf generation failed")
            return "(leaf generation failed)"

    _MODULE_START_ACTIONS = {
        "start", "guide", "init", "open", "upload", "confirm",
        "choose", "prepare", "run_step", "waiting", "hitl", "wait",
    }

    _MODULE_END_ACTIONS = {
        "finish", "done", "complete", "completed", "close", "approval_pass",
    }

    @staticmethod
    def _has_open_module_flow(messages: list[dict[str, Any]]) -> bool:
        """Check if messages contain a module_skill_runtime flow that started but didn't finish."""
        open_modules: set[str] = set()
        for msg in messages:
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                if fn.get("name") != "module_skill_runtime":
                    continue
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        import json
                        args = json.loads(args)
                    except Exception:
                        continue
                if not isinstance(args, dict):
                    continue
                mid = args.get("module_id", "")
                action = str(args.get("action", "")).lower()
                if action in MemoryConsolidator._MODULE_END_ACTIONS:
                    open_modules.discard(mid)
                elif action in MemoryConsolidator._MODULE_START_ACTIONS:
                    open_modules.add(mid)
        return len(open_modules) > 0

    async def compact(
        self,
        session: Session,
        trigger: str = "auto",
        extra_instructions: str = "",
        *,
        boundary_override: int | None = None,
        keep_recent: int | None = None,
    ) -> CompactResult:
        """Unified compact: archive old messages, generate leaf, replace session.messages."""
        if not session.messages:
            return CompactResult(success=True)

        # 1. PreCompact hooks
        extra_instructions = ""
        if self.hook_runner:
            hook_result = await self.hook_runner.run_pre_compact(trigger, {
                "trigger": trigger,
                "session_key": session.key,
                "message_count": len(session.messages),
            })
            if not hook_result.proceed:
                logger.info("Compact aborted by pre-compact hook for {}", session.key)
                return CompactResult(success=False)
            extra_instructions = hook_result.extra_instructions

        # 2. Determine compression range
        if boundary_override is not None:
            end_idx = boundary_override
        elif keep_recent is not None:
            end_idx = max(0, len(session.messages) - keep_recent)
        else:
            estimated, _ = self.estimate_session_prompt_tokens(session)
            budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
            target = budget // 2
            boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
            if boundary is None:
                return CompactResult(success=False)
            end_idx = boundary[0]

        chunk = session.messages[:end_idx]
        retained = session.messages[end_idx:]
        if not chunk:
            return CompactResult(success=False)

        # Skip compact if boundary would split an open module flow
        combined = chunk[-5:] + retained[:5] if retained else chunk[-10:]
        if self._has_open_module_flow(combined):
            logger.info(
                "Compact skipped for {}: open module_skill_runtime flow detected near boundary",
                session.key,
            )
            return CompactResult(success=False)

        # 3. Store in SQLite archive
        range_id: int | None = None
        if self.archive:
            try:
                range_id = self.archive.store_messages(
                    conversation_id=session.key,
                    messages=chunk,
                    summary_text="(pending)",
                    trigger_type=trigger,
                    start_idx=0,
                )
            except Exception:
                logger.exception("SQLite archive store failed")
                range_id = None

        # 4. Generate leaf summary (always range-bound from archived chunk)
        leaf_text = await self._generate_leaf(chunk, extra_instructions)

        # 5. Build compact message
        now = datetime.now().isoformat()
        compact_msg: dict[str, Any] = {
            "role": "user",
            "content": (
                f"[COMPACT] 以下是对 {len(chunk)} 条早期对话的压缩摘要：\n\n"
                f"{leaf_text}\n\n"
                f"如需查看具体细节，可使用 recall_context 工具搜索。"
            ),
            "_meta": {
                "type": "compact_summary",
                "archived_range_id": range_id,
                "messages_archived": len(chunk),
                "compression_timestamp": now,
            },
            "timestamp": now,
        }

        # 6. Replace session.messages
        session.messages = [compact_msg] + retained
        session.last_consolidated = 0
        self.sessions.save(session)

        # 7. Update SQLite summary
        if self.archive and range_id is not None:
            try:
                self.archive.update_summary(range_id, leaf_text)
            except Exception:
                logger.exception("SQLite archive summary update failed")

        logger.info(
            "Compact done for {}: archived {} msgs, trigger={}, range_id={}",
            session.key, len(chunk), trigger, range_id,
        )

        # 8. PostCompact hooks
        if self.hook_runner:
            await self.hook_runner.run_post_compact(trigger, {
                "trigger": trigger,
                "session_key": session.key,
                "summary": leaf_text[:500],
                "messages_archived": len(chunk),
                "range_id": range_id,
            })

        self._consecutive_failures = 0
        return CompactResult(
            success=True,
            messages_archived=len(chunk),
            tokens_before=0,
            tokens_after=0,
            summary_preview=leaf_text[:500],
            range_id=range_id,
        )

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within safe budget.

        Consolidation triggers at 65 % of the context window (not 100 %) to
        leave headroom for large tool outputs produced during the *current* turn.
        Without this early trigger, a long Excel-processing session can push the
        total request body above gateway payload limits mid-turn, returning an
        HTML error page instead of a JSON response.
        """
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
            # New threshold: configurable trigger percent with fixed floor.
            # effective_reserved = max(budget × reserved%, fixed_reserved_tokens)
            # trigger = budget - effective_reserved (fires when estimated >= trigger)
            cfg = self._consolidation_config
            effective_reserved = max(
                int(budget * (100 - cfg.trigger_percent) / 100),
                cfg.fixed_reserved_tokens,
            )
            trigger = budget - effective_reserved
            target = budget // 2
            estimated, source = self.estimate_session_prompt_tokens(session)
            if estimated <= 0:
                return
            if estimated < trigger:
                logger.debug(
                    "Token consolidation idle {}: {}/{} (trigger={}) via {}",
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    trigger,
                    source,
                )
                return

            for round_num in range(self._consolidation_config.max_rounds):
                if estimated <= target:
                    return

                boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
                if boundary is None:
                    logger.debug(
                        "Token consolidation: no safe boundary for {} (round {})",
                        session.key,
                        round_num,
                    )
                    return

                end_idx = boundary[0]
                chunk = session.messages[session.last_consolidated:end_idx]
                if not chunk:
                    return

                logger.info(
                    "Token consolidation round {} for {}: {}/{} via {}, chunk={} msgs",
                    round_num,
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                    len(chunk),
                )
                # Use new compact() if archive is available, else old consolidation
                if self.archive:
                    compact_result = await self.compact(session, trigger="auto", boundary_override=end_idx)
                    if not compact_result.success:
                        return
                    # compact() already saved session and reset last_consolidated
                    # Re-estimate from the new state
                    estimated, source = self.estimate_session_prompt_tokens(session)
                    if estimated <= 0:
                        return
                    continue

                # Legacy path (no archive)
                if not await self.consolidate_messages(chunk):
                    return
                session.last_consolidated = end_idx
                self.sessions.save(session)

                estimated, source = self.estimate_session_prompt_tokens(session)
                if estimated <= 0:
                    return
