"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
import os
import time
from contextlib import AsyncExitStack, nullcontext, suppress
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryConsolidator
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.choices import PresentChoicesTool
from nanobot.agent.tools.user_upload import RequestUserUploadTool
from nanobot.agent.tools.fault_log_intake import PresentFaultLogIntakeCardTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.skills import BUILTIN_SKILLS_DIR
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.module_skill_runtime import ModuleSkillRuntimeTool
from nanobot.agent.tools.site_survey import AnalyzeSiteArtifactsTool
from nanobot.agent.tools.test_sdui_v3 import RunAssetScanTool
from nanobot.agent.tools.email import SendEmailTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.agent.tools.welink import SendWelinkTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.command import CommandContext, CommandRouter, register_builtin_commands
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, EmailToolConfig, ExecToolConfig, WebSearchConfig, WelinkToolConfig
    from nanobot.cron.service import CronService

ToolApprovalCallback = Callable[[Any], Awaitable[bool]]
_APPROVAL_CALLBACK: ContextVar[ToolApprovalCallback | None] = ContextVar(
    "nanobot_tool_approval_cb",
    default=None,
)

# SSE SkillUiDataPatch: bound per /api/chat request (see routes.handle_chat).
SkillUiPatchEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_SKILL_UI_PATCH_EMITTER: ContextVar[SkillUiPatchEmitter | None] = ContextVar(
    "nanobot_skill_ui_patch_emitter",
    default=None,
)

# SSE SkillUiBootstrap: full-document mount for right-side dashboards.
SkillUiBootstrapEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_SKILL_UI_BOOTSTRAP_EMITTER: ContextVar[SkillUiBootstrapEmitter | None] = ContextVar(
    "nanobot_skill_ui_bootstrap_emitter",
    default=None,
)

# SSE SkillUiChatCard: bound per /api/chat request (see routes.handle_chat).
SkillUiChatCardEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_SKILL_UI_CHAT_CARD_EMITTER: ContextVar[SkillUiChatCardEmitter | None] = ContextVar(
    "nanobot_skill_ui_chat_card_emitter",
    default=None,
)

_CURRENT_THREAD_ID: ContextVar[str | None] = ContextVar("nanobot_current_thread_id", default=None)


# ── Hermes flow boundary detection constants ───────────────────────────

_HERMES_FLOW_START_ACTIONS = {
    "guide", "start", "init", "open",
    "choose_strategy", "choose_standard",
}

_HERMES_FLOW_END_ACTIONS = {
    "finish", "done", "complete", "completed",
    "submit", "close", "end",
}

_HERMES_FLOW_WAITING_HINTS = {
    "upload", "confirm", "choose", "hitl", "wait",
}


@dataclass
class HermesReviewScope:
    """Result of flow-aware scope analysis for a Hermes review trigger."""

    status: Literal["complete", "expanded_complete", "partial_deferred"]
    session_key: str
    start_idx: int
    end_idx: int
    trigger_idx: int
    messages: list[dict]
    module_id: str | None = None
    flow_key: str | None = None
    partial_reason: str | None = None
    open_action: str | None = None
    close_action: str | None = None
    expanded_backward: int = 0
    expanded_forward: int = 0
    marker_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

# Web chat: optional PendingHitlStore for agent-driven HITL (request_user_upload).
_PENDING_HITL_STORE: ContextVar[Any | None] = ContextVar("nanobot_pending_hitl_store", default=None)

# DocManager for MissionControl chat cards (optional; often None in /api/chat).
_CHAT_DOCMAN: ContextVar[Any | None] = ContextVar("nanobot_chat_docman", default=None)

# SSE ModuleSessionFocus: 工具级模块焦点（见 routes.handle_chat、module_skill_runtime）
ModuleSessionFocusEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_MODULE_SESSION_FOCUS_EMITTER: ContextVar[ModuleSessionFocusEmitter | None] = ContextVar(
    "nanobot_module_session_focus_emitter",
    default=None,
)

# SSE TaskStatusUpdate: project-level progress payload for top bar / project overview.
TaskStatusEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_TASK_STATUS_EMITTER: ContextVar[TaskStatusEmitter | None] = ContextVar(
    "nanobot_task_status_emitter",
    default=None,
)

# SSE SkillAgentTaskResult: ephemeral structured result for preview insight / hybrid RPC.
SkillAgentTaskResultEmitter = Callable[[dict[str, Any]], Awaitable[None]]
_SKILL_AGENT_TASK_RESULT_EMITTER: ContextVar[SkillAgentTaskResultEmitter | None] = ContextVar(
    "nanobot_skill_agent_task_result_emitter",
    default=None,
)


def get_current_thread_id() -> str | None:
    """Thread id for the active /api/chat request (None outside web chat)."""
    return _CURRENT_THREAD_ID.get()


def get_pending_hitl_store() -> Any | None:
    return _PENDING_HITL_STORE.get()


def get_chat_docman() -> Any | None:
    return _CHAT_DOCMAN.get()


async def emit_skill_ui_chat_card_event(payload: dict[str, Any]) -> None:
    """Push SkillUiChatCard to the current SSE stream; no-op if emitter unbound."""
    cb = _SKILL_UI_CHAT_CARD_EMITTER.get()
    if cb is None:
        logger.info("skill_ui_chat_card_emit_skipped | reason=no_sse_emitter")
        return
    try:
        await cb(payload)
    except Exception:
        logger.exception("skill_ui_chat_card_emit_failed")


async def emit_module_session_focus_event(payload: dict[str, Any]) -> None:
    """Emit ModuleSessionFocus SSE (threadId, moduleId, status=running|idle). No-op if unbound."""
    cb = _MODULE_SESSION_FOCUS_EMITTER.get()
    if cb is None:
        logger.debug("module_session_focus_emit_skipped | reason=no_sse_emitter")
        return
    try:
        await cb(payload)
    except Exception:
        logger.exception("module_session_focus_emit_failed")


async def emit_task_status_event(payload: dict[str, Any]) -> None:
    """Emit TaskStatusUpdate SSE for project-level task progress."""
    cb = _TASK_STATUS_EMITTER.get()
    if cb is None:
        logger.debug("task_status_emit_skipped | reason=no_sse_emitter")
        return
    try:
        await cb(payload)
    except Exception:
        logger.exception("task_status_emit_failed")


async def emit_skill_agent_task_result_event(payload: dict[str, Any]) -> None:
    """Emit SkillAgentTaskResult SSE (structured subtask result; not SDUI state)."""
    cb = _SKILL_AGENT_TASK_RESULT_EMITTER.get()
    if cb is None:
        logger.debug("skill_agent_task_result_emit_skipped | reason=no_sse_emitter")
        return
    try:
        await cb(payload)
    except Exception:
        logger.exception("skill_agent_task_result_emit_failed")


async def emit_skill_ui_bootstrap_event(payload: dict[str, Any]) -> None:
    """Emit SkillUiBootstrap SSE for a full SDUI document mount."""
    cb = _SKILL_UI_BOOTSTRAP_EMITTER.get()
    if cb is None:
        logger.info("skill_ui_bootstrap_emit_skipped | reason=no_sse_emitter")
        return
    try:
        await cb(payload)
    except Exception:
        logger.exception("skill_ui_bootstrap_emit_failed")


async def emit_skill_ui_data_patch_event(payload: dict[str, Any]) -> None:
    """Push a pre-built SkillUiDataPatch payload to the current chat SSE stream.

    No-op when no emitter is bound (e.g. CLI, tests, or non-web channels).

    Typical call flow::

        from nanobot.web.skill_ui_patch import build_skill_ui_data_patch_payload
        payload = await build_skill_ui_data_patch_payload(
            synthetic_path='skill-ui://SduiView?dataFile=workspace/dashboard.json',
            ops=[...],
        )
        await emit_skill_ui_data_patch_event(payload)

    **Logging**: If the SSE emitter is not bound, logs ``reason=no_sse_emitter`` (not in web chat
    context). Path validation failures happen in ``build_skill_ui_data_patch_payload`` and log
    ``reason=invalid_synthetic_path`` there — this function is not reached in that case.
    """
    cb = _SKILL_UI_PATCH_EMITTER.get()
    if cb is None:
        sp = payload.get("syntheticPath") if isinstance(payload, dict) else None
        patch = payload.get("patch") if isinstance(payload, dict) else None
        rev = None
        doc = None
        if isinstance(patch, dict):
            rev = patch.get("revision")
            doc = patch.get("docId")
        logger.info(
            "skill_ui_patch_emit_skipped | reason=no_sse_emitter | "
            "detail=not_in_api_chat_context | syntheticPath={!r} | docId={!r} | revision={!r}",
            (sp or "")[:300],
            doc,
            rev,
        )
        return
    try:
        await cb(payload)
        patch = payload.get("patch") if isinstance(payload, dict) else None
        if isinstance(patch, dict):
            logger.debug(
                "skill_ui_patch_emit_ok | syntheticPath={!r} | docId={!r} | revision={!r}",
                (payload.get("syntheticPath") or "")[:300] if isinstance(payload, dict) else None,
                patch.get("docId"),
                patch.get("revision"),
            )
    except Exception:
        logger.exception(
            "skill_ui_patch_emit_failed | reason=sse_write_error | syntheticPath={!r}",
            (payload.get("syntheticPath") or "")[:300] if isinstance(payload, dict) else None,
        )


async def _run_with_heartbeat(
    coro: "Awaitable[Any]",
    on_heartbeat: "Callable[..., Awaitable[None]]",
    interval: float = 10.0,
) -> Any:
    """Await *coro*, calling *on_heartbeat* every *interval* seconds.

    Uses ``asyncio.wait`` with a timeout so the inner task is never cancelled
    by the per-heartbeat check — only a real CancelledError propagates.
    """
    task: asyncio.Task = asyncio.ensure_future(coro)
    elapsed = 0.0
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                return task.result()
            elapsed += interval
            try:
                await on_heartbeat(f"⏳ 工具执行中，已等待 {int(elapsed)}s…", tool_hint=False)
            except Exception:
                pass
    except asyncio.CancelledError:
        task.cancel()
        raise


def _extract_file_key(tool_name: str, arguments: Any) -> str | None:
    """Return a stable cache key when a tool call references a file path."""
    if not isinstance(arguments, dict):
        return None
    if tool_name == "exec":
        cmd = str(arguments.get("command", ""))
        m = re.search(r"[\w./\\-]+\.(?:xlsx?|csv|json|txt|py|md)", cmd, re.IGNORECASE)
        return f"exec:{m.group(0).lower()}" if m else None
    if tool_name in ("read_file", "write_file", "edit_file"):
        path = str(arguments.get("path", "") or arguments.get("file_path", ""))
        return f"{tool_name}:{path.lower()}" if path else None
    return None


_EXCEL_ERROR_HINT = (
    "\n\n💡 [Excel 读取建议] 请尝试以下方案：\n"
    "① 使用 `openpyxl.load_workbook(path, data_only=True)` 读取计算结果而非公式；\n"
    "② 确认 Excel 文件未被其他程序打开（文件锁定会导致读取失败）；\n"
    "③ 若文件损坏，可先另存为 `.csv` 格式再读取。"
)


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 16_000   # session-persistence limit (unchanged)
    # Per-result limit for the **in-flight** message list sent to the LLM.
    # Keep it small: 14 tool calls × 3500 chars ≈ 49 KB, well under any
    # corporate gateway payload cap and prevents 504 timeouts on large context.
    _INLINE_RESULT_MAX_CHARS = 2_000

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        context_window_tokens: int = 65_536,
        web_search_config: WebSearchConfig | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        email_config: EmailToolConfig | None = None,
        welink_config: WelinkToolConfig | None = None,
    ):
        from nanobot.config.schema import EmailToolConfig, ExecToolConfig, WebSearchConfig, WelinkToolConfig

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.context_window_tokens = context_window_tokens
        self.web_search_config = web_search_config or WebSearchConfig()
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.email_config = email_config or EmailToolConfig()
        self.welink_config = welink_config or WelinkToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self._start_time = time.time()
        self._last_usage: dict[str, int] = {}

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_search_config=self.web_search_config,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._background_tasks: list[asyncio.Task] = []
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._reload_lock = asyncio.Lock()
        # NANOBOT_MAX_CONCURRENT_REQUESTS: <=0 means unlimited; default 3.
        _max = int(os.environ.get("NANOBOT_MAX_CONCURRENT_REQUESTS", "3"))
        self._concurrency_gate: asyncio.Semaphore | None = (
            asyncio.Semaphore(_max) if _max > 0 else None
        )
        # --- Load context config first for subsystem wiring ---
        self._context_config = None
        self._skills_auto_config = None
        try:
            from nanobot.config.loader import load_config
            cfg = load_config()
            self._context_config = cfg.context
            self._skills_auto_config = cfg.skills_auto
        except Exception:
            pass

        from nanobot.config.schema import ContextConfig
        ctx_cfg = self._context_config or ContextConfig()

        self.memory_consolidator = MemoryConsolidator(
            workspace=workspace,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
            max_completion_tokens=provider.generation.max_tokens,
            consolidation_config=ctx_cfg.consolidation,
        )

        # PersistedOutputManager (tool result persistence)
        from nanobot.agent.persisted_output import PersistedOutputManager
        self.persisted_output = PersistedOutputManager(workspace, ctx_cfg.persisted_output)
        # Clean up expired tool-result files on startup
        self.persisted_output.cleanup_expired()

        # MessageArchive (SQLite)
        from nanobot.agent.message_archive import MessageArchive
        self.archive = MessageArchive(workspace, ctx_cfg.message_archive) if ctx_cfg.message_archive.enabled else None

        # HookRunner
        from nanobot.agent.hooks import HookRunner
        self.hook_runner = HookRunner(ctx_cfg.hooks)

        # SessionMemoryExtractor
        from nanobot.agent.session_memory import SessionMemoryExtractor
        self.session_memory = SessionMemoryExtractor(workspace, ctx_cfg.session_memory) if ctx_cfg.session_memory.enabled else None

        # Wire subsystems into MemoryConsolidator
        self.memory_consolidator.wire_subsystems(
            archive=self.archive,
            hook_runner=self.hook_runner,
            session_memory=self.session_memory,
        )

        # Register recall_context tool
        if self.archive:
            from nanobot.agent.tools.recall import RecallContextTool
            self.tools.register(RecallContextTool(self.archive))

        # Hermes skill iteration counter (per-session)
        self._hermes_state: dict[str, dict] = {}  # session_key → state
        self._hermes_epoch: int = 0  # incremented when hermes_enabled or gating config changes

        # Skill change store (SQLite) for Hermes review gate
        from nanobot.agent.skill_change_store import SkillChangeStore
        expiry_days = self._skills_auto_config.request_expiry_days if self._skills_auto_config else 60
        grace_days = self._skills_auto_config.hermes_duplicate_grace_days if self._skills_auto_config else 14
        self.skill_change_store = SkillChangeStore(workspace, expiry_days, duplicate_grace_days=grace_days)
        # P1.1: Recover interrupted review runs from previous process
        try:
            self.skill_change_store.recover_interrupted_review_runs_on_startup()
        except Exception:
            logger.warning("Hermes: startup recovery failed, continuing")
        # Wire LLM provider for semantic judge (updated on reload)
        self.skill_change_store.set_provider(provider, model)

        # Pass skills_auto config to ContextBuilder for filtering and guidance injection
        self.context.set_skills_auto_config(self._skills_auto_config)

        self._register_default_tools()
        self.commands = CommandRouter()
        register_builtin_commands(self.commands)

    async def reload_provider_and_model(
        self,
        *,
        provider: LLMProvider,
        model: str | None = None,
    ) -> None:
        """Hot-reload runtime provider/model.

        This updates all long-lived components that retain provider/model
        references (subagents, memory consolidator). Callers should avoid
        invoking this while a chat run is in progress.
        """
        async with self._reload_lock:
            self.provider = provider
            if model and model.strip():
                self.model = model.strip()

            # Subagents retain their own provider/model references.
            self.subagents.provider = provider
            self.subagents.model = self.model

            # Memory consolidation uses provider/model for summarization and token estimation.
            self.memory_consolidator.provider = provider
            self.memory_consolidator.model = self.model

            # Update skill change store's LLM provider for semantic judge
            if hasattr(self, 'skill_change_store'):
                self.skill_change_store.set_provider(provider, self.model)
            self.memory_consolidator.max_completion_tokens = provider.generation.max_tokens

    async def reload_tool_config(
        self,
        *,
        email_config: "EmailToolConfig | None" = None,
        welink_config: "WelinkToolConfig | None" = None,
    ) -> None:
        """Hot-reload email / welink tool registration based on updated config."""
        from nanobot.config.schema import EmailToolConfig, WelinkToolConfig

        async with self._reload_lock:
            if email_config is not None:
                self.email_config = email_config
                self.tools.unregister("send_email")
                if email_config.enable:
                    self.tools.register(SendEmailTool(config=email_config, workspace=self.workspace))

            if welink_config is not None:
                self.welink_config = welink_config
                self.tools.unregister("send_welink")
                if welink_config.enable:
                    self.tools.register(SendWelinkTool(config=welink_config))

    def reload_skills_auto_config(self) -> bool:
        """Hot-reload skills_auto config (hermes_enabled, nudge_interval, etc).

        Returns True if a meaningful config change was detected (epoch bumped).
        Does NOT: scan history, trigger review, delete pending, or interrupt
        in-flight model calls. Changes take effect from the next turn.
        """
        try:
            from nanobot.config.loader import load_config
            new_cfg = load_config().skills_auto
        except Exception:
            return False

        old_cfg = self._skills_auto_config
        self._skills_auto_config = new_cfg

        # Propagate to context builder for system prompt guidance
        self.context.set_skills_auto_config(new_cfg)

        # Rebuild tool registry: register or unregister skill_manage
        from nanobot.agent.tools.skill_manage import SkillManageTool
        if new_cfg and new_cfg.hermes_enabled:
            if not self.tools.get("skill_manage"):
                self.tools.register(SkillManageTool(
                    workspace=self.workspace,
                    change_store=self.skill_change_store,
                ))
        else:
            self.tools.unregister("skill_manage")

        # Detect meaningful changes that require epoch bump
        _GATING_FIELDS = (
            "hermes_enabled", "hermes_nudge_interval", "hermes_cooldown_turns",
            "hermes_max_pending", "hermes_max_reviews_per_session",
        )
        bumped = False
        if old_cfg is None or new_cfg is None:
            bumped = (old_cfg is not None) != (new_cfg is not None)
        else:
            for field in _GATING_FIELDS:
                if getattr(old_cfg, field, None) != getattr(new_cfg, field, None):
                    bumped = True
                    break

        if bumped:
            self._hermes_epoch += 1

        return bumped

    def set_tool_approval_callback(self, callback: ToolApprovalCallback | None) -> Token:
        """Bind per-request HITL callback in context-local storage."""
        return _APPROVAL_CALLBACK.set(callback)

    def reset_tool_approval_callback(self, token: Token) -> None:
        _APPROVAL_CALLBACK.reset(token)

    def set_skill_ui_patch_emitter(self, callback: SkillUiPatchEmitter | None) -> Token:
        """Bind per-request SkillUiDataPatch SSE callback (same scope as tool approval)."""
        return _SKILL_UI_PATCH_EMITTER.set(callback)

    def reset_skill_ui_patch_emitter(self, token: Token) -> None:
        _SKILL_UI_PATCH_EMITTER.reset(token)

    def set_skill_ui_bootstrap_emitter(self, callback: SkillUiBootstrapEmitter | None) -> Token:
        return _SKILL_UI_BOOTSTRAP_EMITTER.set(callback)

    def reset_skill_ui_bootstrap_emitter(self, token: Token) -> None:
        _SKILL_UI_BOOTSTRAP_EMITTER.reset(token)

    def set_skill_ui_chat_card_emitter(self, callback: SkillUiChatCardEmitter | None) -> Token:
        return _SKILL_UI_CHAT_CARD_EMITTER.set(callback)

    def reset_skill_ui_chat_card_emitter(self, token: Token) -> None:
        _SKILL_UI_CHAT_CARD_EMITTER.reset(token)

    def set_current_thread_id(self, thread_id: str) -> Token:
        return _CURRENT_THREAD_ID.set(thread_id)

    def reset_current_thread_id(self, token: Token) -> None:
        _CURRENT_THREAD_ID.reset(token)

    def set_pending_hitl_store(self, store: Any | None) -> Token:
        return _PENDING_HITL_STORE.set(store)

    def reset_pending_hitl_store(self, token: Token) -> None:
        _PENDING_HITL_STORE.reset(token)

    def set_chat_docman(self, docman: Any | None) -> Token:
        return _CHAT_DOCMAN.set(docman)

    def reset_chat_docman(self, token: Token) -> None:
        _CHAT_DOCMAN.reset(token)

    def set_module_session_focus_emitter(self, callback: ModuleSessionFocusEmitter | None) -> Token:
        return _MODULE_SESSION_FOCUS_EMITTER.set(callback)

    def reset_module_session_focus_emitter(self, token: Token) -> None:
        _MODULE_SESSION_FOCUS_EMITTER.reset(token)

    def set_task_status_emitter(self, callback: TaskStatusEmitter | None) -> Token:
        return _TASK_STATUS_EMITTER.set(callback)

    def reset_task_status_emitter(self, token: Token) -> None:
        _TASK_STATUS_EMITTER.reset(token)

    def set_skill_agent_task_result_emitter(
        self, callback: SkillAgentTaskResultEmitter | None
    ) -> Token:
        return _SKILL_AGENT_TASK_RESULT_EMITTER.set(callback)

    def reset_skill_agent_task_result_emitter(self, token: Token) -> None:
        _SKILL_AGENT_TASK_RESULT_EMITTER.reset(token)

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        extra_read = [BUILTIN_SKILLS_DIR] if allowed_dir else None
        self.tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read))
        for cls in (WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        if self.exec_config.enable:
            self.tools.register(ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
            ))
        self.tools.register(WebSearchTool(config=self.web_search_config, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(
            AnalyzeSiteArtifactsTool(
                workspace=self.workspace,
                allowed_dir=allowed_dir,
                extra_allowed_dirs=extra_read,
            )
        )
        self.tools.register(RunAssetScanTool(workspace=self.workspace))
        self.tools.register(ModuleSkillRuntimeTool())
        self.tools.register(PresentChoicesTool())
        self.tools.register(RequestUserUploadTool())
        self.tools.register(PresentFaultLogIntakeCardTool())
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
        if self.email_config.enable:
            self.tools.register(SendEmailTool(
                config=self.email_config,
                workspace=self.workspace,
            ))
        if self.welink_config.enable:
            self.tools.register(SendWelinkTool(config=self.welink_config))

        # Hermes skill_manage tool (conditional on config)
        if self._skills_auto_config and self._skills_auto_config.hermes_enabled:
            from nanobot.agent.tools.skill_manage import SkillManageTool
            self.tools.register(SkillManageTool(
                workspace=self.workspace,
                change_store=self.skill_change_store,
            ))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        session_key: str | None = None,
    ) -> None:
        """Update context for all tools that need routing info."""
        actual_session_key = session_key or f"{channel}:{chat_id}"
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))
        if recall := self.tools.get("recall_context"):
            if hasattr(recall, "set_context"):
                recall.set_context(actual_session_key)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        from nanobot.utils.helpers import strip_think
        return strip_think(text) or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        *,
        channel: str = "cli",
        chat_id: str = "direct",
        message_id: str | None = None,
        model_name: str | None = None,
        session_key: str | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop.

        *on_stream*: called with each content delta during streaming.
        *on_stream_end(resuming)*: called when a streaming session finishes.
        ``resuming=True`` means tool calls follow (spinner should restart);
        ``resuming=False`` means this is the final response.
        """
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        # file-key → consecutive call count (reset when a *different* file is called)
        _file_retry_counter: dict[str, int] = {}

        # Wrap on_stream with stateful think-tag filter so downstream
        # consumers (CLI, channels) never see <think> blocks.
        _raw_stream = on_stream
        _stream_buf = ""

        async def _filtered_stream(delta: str) -> None:
            nonlocal _stream_buf
            from nanobot.utils.helpers import strip_think
            prev_clean = strip_think(_stream_buf)
            _stream_buf += delta
            new_clean = strip_think(_stream_buf)
            incremental = new_clean[len(prev_clean):]
            if incremental and _raw_stream:
                await _raw_stream(incremental)

        while iteration < self.max_iterations:
            iteration += 1

            tool_defs = self.tools.get_definitions()
            current_model = model_name or self.model

            if on_stream:
                # Guard against cold-start latency: fire a heartbeat every 10 s
                # until the first token arrives, so the frontend idle-timeout
                # (20 s) is never triggered while waiting for the LLM to begin.
                llm_started = asyncio.Event()

                async def _guarded_stream(delta: str) -> None:
                    llm_started.set()          # first token → stop heartbeat
                    await _filtered_stream(delta)

                async def _llm_heartbeat() -> None:
                    # Create the wait-task ONCE so we don't leak a new coroutine
                    # every iteration when the 10-second timeout fires.
                    wait_task = asyncio.ensure_future(llm_started.wait())
                    try:
                        while True:
                            done, _ = await asyncio.wait({wait_task}, timeout=10.0)
                            if done:      # event was set; LLM has started streaming
                                break
                            if on_progress:
                                try:
                                    await on_progress("⏳ 等待模型响应中…", tool_hint=False)
                                except Exception:
                                    pass
                    finally:
                        wait_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await wait_task

                _heartbeat_task = asyncio.create_task(_llm_heartbeat())
                try:
                    response = await self.provider.chat_stream_with_retry(
                        messages=messages,
                        tools=tool_defs,
                        model=current_model,
                        on_content_delta=_guarded_stream,
                    )
                finally:
                    llm_started.set()          # unblock heartbeat loop on any exit
                    _heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await _heartbeat_task
            else:
                response = await self.provider.chat_with_retry(
                    messages=messages,
                    tools=tool_defs,
                    model=current_model,
                )

            usage = response.usage or {}
            self._last_usage = {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            }

            if response.has_tool_calls:
                if on_stream and on_stream_end:
                    await on_stream_end(resuming=True)
                    _stream_buf = ""

                if on_progress:
                    if not on_stream:
                        thought = self._strip_think(response.content)
                        if thought:
                            await on_progress(thought)
                    tool_hint = self._tool_hint(response.tool_calls)
                    tool_hint = self._strip_think(tool_hint)
                    await on_progress(tool_hint, tool_hint=True)

                tool_call_dicts = [
                    tc.to_openai_tool_call()
                    for tc in response.tool_calls
                ]
                # ── Truncate large tool-call arguments in the in-flight context ──
                # write_file / edit_file calls embed full file contents as
                # arguments (e.g. a 200-line Python script).  Those strings live
                # in the assistant message's tool_calls[].function.arguments and
                # are never pruned by our tool-result truncation, silently
                # ballooning the request body and causing 504 gateway timeouts.
                # We replace oversized argument values with a short placeholder
                # so the LLM still sees the call structure but not the bulk payload.
                _ARG_INLINE_LIMIT = 250  # chars; full script visible in actual file
                inline_tool_call_dicts: list[dict] = []
                for tcd in tool_call_dicts:
                    func = tcd.get("function", {})
                    raw_args = func.get("arguments", "{}")
                    if isinstance(raw_args, str) and len(raw_args) > _ARG_INLINE_LIMIT:
                        try:
                            parsed = json.loads(raw_args)
                            for k, v in parsed.items():
                                if isinstance(v, str) and len(v) > _ARG_INLINE_LIMIT:
                                    parsed[k] = (
                                        f"[内容已省略 ({len(v)} 字符)，工具已收到完整内容]"
                                    )
                            compacted = {**tcd, "function": {**func, "arguments": json.dumps(parsed, ensure_ascii=False)}}
                        except Exception:
                            compacted = tcd
                        inline_tool_call_dicts.append(compacted)
                    else:
                        inline_tool_call_dicts.append(tcd)
                messages = self.context.add_assistant_message(
                    messages, response.content, inline_tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tc in response.tool_calls:
                    tools_used.append(tc.name)
                    args_str = json.dumps(tc.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tc.name, args_str[:200])

                    # Hermes: track iterations since last skill_manage call (session-scoped)
                    if session_key and self._skills_auto_config and self._skills_auto_config.hermes_enabled:
                        hs = self._get_hermes_state(session_key)
                        if tc.name == "skill_manage":
                            hs["iters_since_skill_manage"] = 0
                        else:
                            hs["iters_since_skill_manage"] += 1

                # Re-bind tool context right before execution so that
                # concurrent sessions don't clobber each other's routing.
                self._set_tool_context(channel, chat_id, message_id, session_key=session_key)

                approval_cb = _APPROVAL_CALLBACK.get()
                approved_calls = []
                result_by_id: dict[str, Any] = {}

                for tc in response.tool_calls:
                    approved = True
                    if approval_cb is not None:
                        approved = await approval_cb(tc)
                    if approved:
                        approved_calls.append(tc)
                    else:
                        result_by_id[tc.id] = "Tool call cancelled by user approval."

                # Execute approved tool calls concurrently — the LLM batches
                # independent calls in a single response on purpose.
                # return_exceptions=True ensures all results are collected
                # even if one tool is cancelled or raises BaseException.
                if approved_calls:
                    # Count per-file retries before execution
                    for tc in approved_calls:
                        fkey = _extract_file_key(tc.name, tc.arguments)
                        if fkey:
                            _file_retry_counter[fkey] = _file_retry_counter.get(fkey, 0) + 1

                    gather_coro = asyncio.gather(*(
                        self.tools.execute(tc.name, tc.arguments, _nanobot_tool_call_id=tc.id)
                        for tc in approved_calls
                    ), return_exceptions=True)

                    # Wrap with heartbeat so long-running execs don't trigger
                    # the frontend SSE idle timeout (~20 s).
                    if on_progress:
                        results = await _run_with_heartbeat(
                            gather_coro, on_progress, interval=10.0
                        )
                    else:
                        results = await gather_coro

                    for tc, result in zip(approved_calls, results):
                        result_by_id[tc.id] = result

                for tool_call in response.tool_calls:
                    result = result_by_id.get(tool_call.id, "Tool call cancelled by user approval.")
                    if isinstance(result, BaseException):
                        result = f"Error: {type(result).__name__}: {result}"

                    # ── Inject file-retry warning ──
                    if isinstance(result, str):
                        fkey = _extract_file_key(tool_call.name, tool_call.arguments)
                        if fkey and _file_retry_counter.get(fkey, 0) > 3:
                            result += (
                                "\n\n⚠️ [系统提示] 检测到对同一文件的重试已超过 3 次，"
                                "请检查：文件是否被占用、路径是否正确，"
                                "或尝试先用 dir/ls 命令确认文件存在。"
                            )

                        # ── Inject Excel/openpyxl hint ──
                        args_str = str(tool_call.arguments or "").lower()
                        is_excel_op = ".xls" in args_str
                        has_error = (
                            "openpyxl" in result.lower()
                            or "xlrd" in result.lower()
                            or (is_excel_op and (
                                "error" in result.lower() or "traceback" in result.lower()
                            ))
                        )
                        if has_error:
                            result += _EXCEL_ERROR_HINT

                    # ── Tool result handling (PersistedOutput) ─────────────────
                    inline_result = result
                    if isinstance(inline_result, str):
                        if self.persisted_output.should_persist(
                            inline_result, tool_call.name, tool_call.id
                        ):
                            inline_result = self.persisted_output.persist(
                                inline_result, tool_call.id, tool_call.name
                            )
                        elif len(inline_result) > self._INLINE_RESULT_MAX_CHARS:
                            inline_result = self.persisted_output.truncate_inline(
                                inline_result, self._INLINE_RESULT_MAX_CHARS
                            )
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, inline_result
                    )

                # ── Stop turn after present_choices ──────────────────────────
                # present_choices signals that we need user input before
                # proceeding.  Break immediately so the frontend receives
                # RunFinished (with the choices payload already captured by
                # on_tool_approval in routes.py) and can render the modal.
                # Do NOT call on_stream_end here — let the normal post-loop
                # path in the caller (routes.py) send RunFinished so that
                # run_finished_sent is managed in exactly one place.
                if any(tc.name == "present_choices" for tc in response.tool_calls):
                    final_content = ""  # choices turn; caller includes run_choices
                    break
                if any(tc.name == "request_user_upload" for tc in response.tool_calls):
                    final_content = ""
                    break
                # ─────────────────────────────────────────────────────────────
            else:
                if on_stream and on_stream_end:
                    await on_stream_end(resuming=False)
                    _stream_buf = ""

                clean = self._strip_think(response.content)
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                # Preserve real task cancellation so shutdown can complete cleanly.
                # Only ignore non-task CancelledError signals that may leak from integrations.
                if not self._running or asyncio.current_task().cancelling():
                    raise
                continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            raw = msg.content.strip()
            if self.commands.is_priority(raw):
                ctx = CommandContext(msg=msg, session=None, key=msg.session_key, raw=raw, loop=self)
                result = await self.commands.dispatch_priority(ctx)
                if result:
                    await self.bus.publish_outbound(result)
                continue
            task = asyncio.create_task(self._dispatch(msg))
            self._active_tasks.setdefault(msg.session_key, []).append(task)
            task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message: per-session serial, cross-session concurrent."""
        lock = self._session_locks.setdefault(msg.session_key, asyncio.Lock())
        gate = self._concurrency_gate or nullcontext()
        async with lock, gate:
            try:
                on_stream = on_stream_end = None
                if msg.metadata.get("_wants_stream"):
                    async def on_stream(delta: str) -> None:
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content=delta, metadata={"_stream_delta": True},
                        ))

                    async def on_stream_end(*, resuming: bool = False) -> None:
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content="", metadata={"_stream_end": True, "_resuming": resuming},
                        ))

                response = await self._process_message(
                    msg, on_stream=on_stream, on_stream_end=on_stream_end,
                )
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Drain pending background archives, then close MCP connections."""
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def _get_hermes_state(self, session_key: str) -> dict:
        """Return (creating if needed) per-session Hermes tracking state.

        Uses LRU eviction: recently accessed entries survive, stale ones are pruned.
        Each entry tracks last_seen_at for proper LRU ordering.

        If the global epoch has advanced (config changed), the entry is
        lazy-reset so counting starts fresh from the new configuration.
        """
        now = __import__("time").time()
        if len(self._hermes_state) > 100:
            # LRU eviction: sort by last_seen_at ascending, remove the stalest 50
            sorted_keys = sorted(
                self._hermes_state,
                key=lambda k: self._hermes_state[k].get("last_seen_at", 0),
            )
            for k in sorted_keys[:50]:
                del self._hermes_state[k]

        cooldown_turns = (
            self._skills_auto_config.hermes_cooldown_turns
            if self._skills_auto_config else 5
        )

        if session_key not in self._hermes_state:
            self._hermes_state[session_key] = {
                "iters_since_skill_manage": 0,
                "user_turns_since_review": cooldown_turns,
                "reviews_this_session": 0,
                "active_review_run_id": None,
                "last_seen_at": now,
                "epoch": self._hermes_epoch,
            }
        else:
            entry = self._hermes_state[session_key]
            entry["last_seen_at"] = now
            # Lazy epoch reset: config changed since last access
            if entry.get("epoch", 0) != self._hermes_epoch:
                entry["iters_since_skill_manage"] = 0
                entry["reviews_this_session"] = 0
                entry["user_turns_since_review"] = cooldown_turns
                entry["epoch"] = self._hermes_epoch
        return self._hermes_state[session_key]

    def _consume_review_trigger(self, run_id: str, consume: tuple[int, int]) -> None:
        """Consume the trigger debt: reset counters for the consumed amount."""
        trigger_iters, trigger_user_turns = consume
        try:
            run = self.skill_change_store.get_review_run(run_id)
            if not run:
                return
            hs = self._get_hermes_state(run.session_key)
            hs["iters_since_skill_manage"] = max(0, hs["iters_since_skill_manage"] - trigger_iters)
            hs["user_turns_since_review"] = 0
            hs["reviews_this_session"] += 1
        except Exception:
            logger.warning("Hermes: failed to consume review trigger for run {}", run_id)

    def _clear_active_review(self, run_id: str) -> None:
        """Clear active_review_run_id for the session that owns this run."""
        if not run_id:
            return
        try:
            run = self.skill_change_store.get_review_run(run_id)
            if not run:
                return
            hs = self._get_hermes_state(run.session_key)
            if hs.get("active_review_run_id") == run_id:
                hs["active_review_run_id"] = None
        except Exception:
            pass

    @staticmethod
    def _distill_for_review(messages: list[dict]) -> list[dict]:
        """Distill raw session messages into a compact form for the Hermes review agent.

        - User messages: kept intact (capped at 4000 chars)
        - Assistant messages: text reasoning kept (capped at 800 chars);
          pure tool-call messages compressed to a called-tools list
        - Tool messages: structured summary with head/tail/error extraction
        """
        import re as _re

        _ERROR_RE = _re.compile(
            r"(?i)(traceback|error|failed|exception|assertion|denied|permission"
            r"|not found|401|403|500|fatal|panic|segfault)",
        )
        _TEST_RESULT_RE = _re.compile(r"(\d+)\s+(passed|failed|error|warning)", _re.IGNORECASE)
        _FILE_PATH_RE = _re.compile(r"(?:^|\s)([\w./\-]+\.[\w]+)(?::(\d+))?", _re.MULTILINE)
        _SENSITIVE_RE = _re.compile(
            r"(?i)((?:authorization|bearer|api[_-]?key|token|password|secret|credential|private[_-]?key|cookie)"
            r"\s*[:=]\s*).+",
        )

        def _redact(text: str) -> str:
            return _SENSITIVE_RE.sub(r"\1***", text)

        def _summarize_tool(name: str, content: str) -> str:
            if len(content) <= 600:
                return _redact(content)
            head = _redact(content[:300])
            tail = _redact(content[-300:])
            lines = content.split("\n")
            error_lines = [l for l in lines if _ERROR_RE.search(l)]
            error_excerpt = _redact("\n".join(error_lines[-5:])) if error_lines else ""
            test_results = _TEST_RESULT_RE.findall(content)
            file_paths = [m[0] for m in _FILE_PATH_RE.findall(content)][:5]
            summary = {
                "tool": name,
                "head": head,
                "tail": tail,
                "errors": error_excerpt[:300] or None,
                "test_results": " ".join(f"{n} {s}" for n, s in test_results) or None,
                "file_paths": file_paths or None,
                "truncated": True,
                "original_chars": len(content),
            }
            return json.dumps(summary, ensure_ascii=False)

        distilled: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    distilled.append({"role": "user", "content": content[:4000]})
            elif role == "assistant":
                content = msg.get("content")
                tool_calls = msg.get("tool_calls")
                if isinstance(content, str) and content.strip():
                    distilled.append({"role": "assistant", "content": content[:800]})
                elif tool_calls:
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    distilled.append({
                        "role": "assistant",
                        "content": f"Called tools: {', '.join(names)}",
                    })
            elif role == "tool":
                tool_name = msg.get("name", "")
                content = msg.get("content", "")
                if isinstance(content, str):
                    summary = _summarize_tool(tool_name, content)
                    distilled.append({
                        "role": "assistant",
                        "content": f"[Tool summary: {tool_name}]\n{summary}",
                    })
        # Global size cap: keep early user messages + recent context
        MAX_REVIEW_CHARS = 50_000
        total = sum(len(m.get("content", "")) for m in distilled)
        if total > MAX_REVIEW_CHARS:
            # Keep first 10% (early user intent) and last 60% (recent actions)
            head_end = max(1, int(len(distilled) * 0.1))
            tail_start = max(head_end, int(len(distilled) * 0.4))
            head = distilled[:head_end]
            tail = distilled[tail_start:]
            # Drop from the middle of tail until under budget
            while tail and sum(len(m.get("content", "")) for m in head) + sum(len(m.get("content", "")) for m in tail) > MAX_REVIEW_CHARS:
                tail.pop(0)
            distilled = head + tail
        return distilled

    @staticmethod
    def _build_review_evidence_summary(
        distilled_messages: list[dict],
        hermes_state: dict | None = None,
        pending_count: int = 0,
    ) -> str:
        """Build a Chinese evidence summary explaining why Hermes triggered this review.

        Extracts user intent, corrections, tool errors, and trigger context into a
        compact human-readable summary (max ~8K chars).
        """
        import re as _re

        _SENSITIVE_RE = _re.compile(
            r"(?i)((?:authorization|bearer|api[_-]?key|token|password|secret|credential|private[_-]?key|cookie)"
            r"\s*[:=]\s*).+",
        )

        def _redact(text: str) -> str:
            return _SENSITIVE_RE.sub(r"\1***", text)

        sections: list[str] = []

        # 1. User intent (early user messages)
        user_msgs = [m for m in distilled_messages if m.get("role") == "user"]
        if user_msgs:
            intent_lines = []
            for m in user_msgs[:3]:
                content = str(m.get("content", ""))[:500]
                content = _redact(content)
                intent_lines.append(f"- {content}")
            sections.append("【用户意图】\n" + "\n".join(intent_lines))

        # 2. Recent user corrections / preferences
        correction_keywords = ("以后", "不要", "记住", "下次", "应该", "记得", "下次注意",
                               "always", "never", "remember", "should", "don't", "avoid")
        corrections = []
        for m in user_msgs[-5:]:
            content = str(m.get("content", ""))
            if any(kw in content.lower() for kw in correction_keywords):
                corrections.append(f"- {_redact(content[:300])}")
        if corrections:
            sections.append("【用户偏好/纠正】\n" + "\n".join(corrections[:5]))

        # 3. Key tool behaviors (errors, test results)
        tool_msgs = [m for m in distilled_messages
                     if m.get("role") == "assistant" and m.get("content", "").startswith("[Tool summary:")]
        if tool_msgs:
            tool_lines = []
            for m in tool_msgs[-8:]:
                content = str(m.get("content", ""))
                # Try to extract errors from JSON summary
                try:
                    json_part = content.split("\n", 1)[1]
                    parsed = json.loads(json_part)
                    parts = [f"工具: {parsed.get('tool', '?')}"]
                    if parsed.get("errors"):
                        parts.append(f"错误: {parsed['errors'][:200]}")
                    if parsed.get("test_results"):
                        parts.append(f"测试结果: {parsed['test_results'][:200]}")
                    if parsed.get("file_paths"):
                        parts.append(f"文件: {', '.join(str(p) for p in parsed['file_paths'][:3])}")
                    tool_lines.append("- " + " | ".join(parts))
                except (json.JSONDecodeError, IndexError):
                    tool_lines.append(f"- {_redact(content[:200])}")
            if tool_lines:
                sections.append("【关键工具行为】\n" + "\n".join(tool_lines[:8]))

        # 4. Trigger context
        if hermes_state:
            trigger_info = [
                f"- 距上次技能管理的迭代次数: {hermes_state.get('iters_since_skill_manage', '?')}",
                f"- 距上次审核的用户轮次: {hermes_state.get('user_turns_since_review', '?')}",
                f"- 本会话审核次数: {hermes_state.get('reviews_this_session', '?')}",
                f"- 当前待审核请求数: {pending_count}",
            ]
            sections.append("【触发原因】\n" + "\n".join(trigger_info))

        result = "\n\n".join(sections)

        # Cap at 8K chars, preserving early sections first
        MAX_EVIDENCE_CHARS = 8000
        if len(result) > MAX_EVIDENCE_CHARS:
            # Truncate from the end
            result = result[:MAX_EVIDENCE_CHARS]

        return result

    # ── Hermes scope expansion helpers ─────────────────────────────────────

    @staticmethod
    def _extract_module_skill_runtime_call(msg: dict) -> dict[str, str] | None:
        """Extract module_id and action from a module_skill_runtime tool call."""
        if msg.get("role") != "assistant":
            return None
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return None
        for tc in tool_calls:
            func = tc.get("function", {})
            if func.get("name") == "module_skill_runtime":
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        return None
                if not isinstance(args, dict):
                    return None
                module_id = args.get("module_id")
                action = args.get("action")
                if module_id and action:
                    return {"module_id": module_id, "action": action}
        return None

    @staticmethod
    def _is_flow_start_action(action: str) -> bool:
        lower = action.lower()
        return lower in _HERMES_FLOW_START_ACTIONS or lower.endswith("_start")

    @staticmethod
    def _is_flow_end_action(action: str) -> bool:
        lower = action.lower()
        return lower in _HERMES_FLOW_END_ACTIONS or lower.endswith("_finish") or lower.endswith("_complete")

    @staticmethod
    def _is_flow_waiting_action(action: str) -> bool:
        lower = action.lower()
        return any(h in lower for h in _HERMES_FLOW_WAITING_HINTS)

    def _build_hermes_review_scope(
        self,
        *,
        session: Session,
        session_key: str,
        trigger_idx: int | None = None,
        marker: Any = None,
    ) -> HermesReviewScope:
        """Analyze session messages to determine if Hermes should defer review
        due to an incomplete module_skill_runtime flow."""
        messages = session.messages
        if trigger_idx is None:
            trigger_idx = len(messages) - 1

        cfg = self._skills_auto_config

        # Logic A: if scope expand not enabled, return full session
        if not cfg or not getattr(cfg, "hermes_scope_expand_enabled", False):
            return HermesReviewScope(
                status="complete",
                session_key=session_key,
                start_idx=0,
                end_idx=len(messages) - 1,
                trigger_idx=trigger_idx,
                messages=messages,
            )

        back_limit = getattr(cfg, "hermes_scope_expand_back_messages", 40)
        back_user_turns = getattr(cfg, "hermes_scope_expand_back_user_turns", 4)
        forward_limit = getattr(cfg, "hermes_scope_expand_forward_messages", 40)

        # Logic B: marker resume path
        if marker is not None:
            start_idx = marker.start_msg_idx
            module_id = marker.module_id
            # Scan from start_idx to end for same module_id end action
            scan_end = min(len(messages), marker.last_seen_msg_idx + forward_limit + 1)
            end_idx = None
            for i in range(start_idx, scan_end):
                parsed = self._extract_module_skill_runtime_call(messages[i])
                if parsed and parsed["module_id"] == module_id:
                    if self._is_flow_end_action(parsed["action"]):
                        end_idx = i
                        break

            if end_idx is not None:
                scope_msgs = messages[start_idx:end_idx + 1]
                flow_key = f"{session_key}:{module_id}:{start_idx}"
                return HermesReviewScope(
                    status="expanded_complete",
                    session_key=session_key,
                    start_idx=start_idx,
                    end_idx=end_idx,
                    trigger_idx=trigger_idx,
                    messages=scope_msgs,
                    module_id=module_id,
                    flow_key=flow_key,
                    close_action="finish",
                    expanded_backward=0,
                    expanded_forward=end_idx - marker.last_seen_msg_idx,
                    marker_id=marker.id if hasattr(marker, "id") else None,
                )
            else:
                # Still incomplete, update marker
                flow_key = getattr(marker, "flow_key", None) or f"{session_key}:{module_id}:unknown:{trigger_idx}"
                return HermesReviewScope(
                    status="partial_deferred",
                    session_key=session_key,
                    start_idx=start_idx,
                    end_idx=trigger_idx,
                    trigger_idx=trigger_idx,
                    messages=[],
                    module_id=module_id,
                    flow_key=flow_key,
                    partial_reason="missing_end",
                    marker_id=marker.id if hasattr(marker, "id") else None,
                )

        # Logic C: normal trigger — scan backward for module_skill_runtime calls
        scan_start = max(0, trigger_idx - back_limit)
        # Also count user turns in the scan range
        user_turn_count = 0
        recent_module_calls: list[tuple[int, str, str]] = []  # (idx, module_id, action)

        for i in range(trigger_idx, max(-1, scan_start - 1), -1):
            if i < 0:
                break
            msg = messages[i]
            if msg.get("role") == "user":
                user_turn_count += 1
                if user_turn_count > back_user_turns:
                    break
            parsed = self._extract_module_skill_runtime_call(msg)
            if parsed:
                recent_module_calls.append((i, parsed["module_id"], parsed["action"]))

        if not recent_module_calls:
            # No module calls found, proceed with full session
            return HermesReviewScope(
                status="complete",
                session_key=session_key,
                start_idx=0,
                end_idx=len(messages) - 1,
                trigger_idx=trigger_idx,
                messages=messages,
            )

        # Analyze the most recent module call
        nearest_idx, module_id, action = recent_module_calls[0]

        # Count total calls for this module_id in range
        module_call_count = sum(1 for _, mid, _ in recent_module_calls if mid == module_id)

        # Find start and end for this module_id
        start_idx = None
        end_idx = None

        for i, mid, act in reversed(recent_module_calls):
            if mid == module_id and self._is_flow_start_action(act):
                start_idx = i
                break

        # Look forward from nearest_idx for end action
        if start_idx is not None:
            for i in range(start_idx, len(messages)):
                parsed = self._extract_module_skill_runtime_call(messages[i])
                if parsed and parsed["module_id"] == module_id:
                    if self._is_flow_end_action(parsed["action"]):
                        end_idx = i
                        break

        # Determine status
        if end_idx is not None:
            # Complete flow found
            actual_start = start_idx if start_idx is not None else nearest_idx
            scope_msgs = messages[actual_start:end_idx + 1]
            flow_key = f"{session_key}:{module_id}:{actual_start}"
            return HermesReviewScope(
                status="expanded_complete",
                session_key=session_key,
                start_idx=actual_start,
                end_idx=end_idx,
                trigger_idx=trigger_idx,
                messages=scope_msgs,
                module_id=module_id,
                flow_key=flow_key,
                open_action=action if start_idx is None else None,
                close_action="finish",
                expanded_backward=trigger_idx - actual_start,
                expanded_forward=0,
            )

        # No end found — check if this is a genuine partial flow
        if start_idx is not None:
            # Have start but no end
            if self._is_flow_waiting_action(action) or module_call_count >= 2:
                flow_key = f"{session_key}:{module_id}:{start_idx}"
                return HermesReviewScope(
                    status="partial_deferred",
                    session_key=session_key,
                    start_idx=start_idx,
                    end_idx=trigger_idx,
                    trigger_idx=trigger_idx,
                    messages=[],
                    module_id=module_id,
                    flow_key=flow_key,
                    partial_reason="missing_end",
                    open_action=action,
                )
            else:
                # Single non-waiting call — don't defer
                return HermesReviewScope(
                    status="complete",
                    session_key=session_key,
                    start_idx=0,
                    end_idx=len(messages) - 1,
                    trigger_idx=trigger_idx,
                    messages=messages,
                )
        else:
            # No start found
            if self._is_flow_waiting_action(action) or module_call_count >= 2:
                flow_key = f"{session_key}:{module_id}:unknown:{trigger_idx}"
                return HermesReviewScope(
                    status="partial_deferred",
                    session_key=session_key,
                    start_idx=nearest_idx,
                    end_idx=trigger_idx,
                    trigger_idx=trigger_idx,
                    messages=[],
                    module_id=module_id,
                    flow_key=flow_key,
                    partial_reason="missing_start",
                    open_action=action,
                )
            else:
                # Single non-waiting, non-start module call — don't defer
                return HermesReviewScope(
                    status="complete",
                    session_key=session_key,
                    start_idx=0,
                    end_idx=len(messages) - 1,
                    trigger_idx=trigger_idx,
                    messages=messages,
                )

    def _schedule_background(self, coro) -> None:
        """Schedule a coroutine as a tracked background task (drained on shutdown)."""
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        task.add_done_callback(self._background_tasks.remove)

    async def _maybe_time_based_compact(self, session: Session) -> None:
        """Check if last assistant message is older than gapThresholdHours, trigger compact."""
        if not self._context_config:
            return
        cfg = self._context_config.time_based_graduated_compact
        if not cfg.enabled:
            return

        # Find last assistant message with timestamp
        last_asst_ts = None
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant" and msg.get("timestamp"):
                last_asst_ts = msg["timestamp"]
                break

        if not last_asst_ts:
            return

        try:
            from datetime import datetime
            if isinstance(last_asst_ts, str):
                last_asst_dt = datetime.fromisoformat(last_asst_ts)
            else:
                return
            gap_hours = (datetime.now() - last_asst_dt).total_seconds() / 3600
        except Exception:
            return

        if gap_hours >= cfg.gap_threshold_hours:
            logger.info("Time-based compact triggered for {} (gap={:.1f}h)", session.key, gap_hours)
            await self.memory_consolidator.compact(
                session, trigger="time", keep_recent=cfg.keep_recent,
            )

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        model_name: str | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            # Pre-turn: run deferred compact check from previous turn
            if session.metadata.pop("compact_check_requested", None):
                await self.memory_consolidator.maybe_consolidate_by_tokens(session)
                self.sessions.save(session)

            # Pre-turn: time-based graduated compact
            if self._context_config and self._context_config.time_based_graduated_compact.enabled:
                await self._maybe_time_based_compact(session)

            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"), session_key=key)
            history = session.get_history(max_messages=None)
            current_role = "assistant" if msg.sender_id == "subagent" else "user"
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
                current_role=current_role,
            )
            final_content, _, all_msgs = await self._run_agent_loop(
                messages, channel=channel, chat_id=chat_id,
                message_id=msg.metadata.get("message_id"),
                model_name=model_name, session_key=key,
            )
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            # Signal pre-turn compact check for next message (non-destructive)
            session.metadata["compact_check_requested"] = True
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Update session_key on SkillManageTool so requests are traceable
        from nanobot.agent.tools.skill_manage import SkillManageTool as _SkillManageTool
        if smt := self.tools.get("skill_manage"):
            if isinstance(smt, _SkillManageTool):
                smt._session_key = key

        # Slash commands
        raw = msg.content.strip()
        ctx = CommandContext(msg=msg, session=session, key=key, raw=raw, loop=self)
        if result := await self.commands.dispatch(ctx):
            return result

        # Pre-turn: run deferred compact check from previous turn's metadata flag
        if session.metadata.pop("compact_check_requested", None):
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            self.sessions.save(session)

        # Pre-turn: time-based graduated compact (24h gap check)
        if self._context_config and self._context_config.time_based_graduated_compact.enabled:
            await self._maybe_time_based_compact(session)

        # Preflight: check current token pressure
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"), session_key=key)
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=None)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            channel=msg.channel, chat_id=msg.chat_id,
            message_id=msg.metadata.get("message_id"),
            model_name=model_name,
            session_key=key,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        # Signal pre-turn compact check for next message (non-destructive)
        session.metadata["compact_check_requested"] = True
        self.sessions.save(session)

        # Background: session memory extraction (deepcopy snapshot)
        if self.session_memory:
            import copy
            snapshot = copy.deepcopy(session.messages)
            sm_model = self._context_config.session_memory.auxiliary_model if self._context_config else None
            self._schedule_background(
                self.session_memory.extract_incremental(session.key, snapshot, self.provider, sm_model)
            )

        # Background: Hermes skill review (auto-create/update skills)
        if self._skills_auto_config and self._skills_auto_config.hermes_enabled:
            cfg = self._skills_auto_config
            try:
                hs = self._get_hermes_state(key)
                pending = self.skill_change_store.pending_count()
            except Exception:
                logger.warning("Hermes: failed to query state, skipping trigger check")
                pending = cfg.hermes_max_pending  # safe default: skip trigger
            else:
                should_trigger = (
                    hs["iters_since_skill_manage"] >= cfg.hermes_nudge_interval
                    and pending < cfg.hermes_max_pending
                    and hs["user_turns_since_review"] >= cfg.hermes_cooldown_turns
                    and hs["reviews_this_session"] < cfg.hermes_max_reviews_per_session
                )

                # P1.1: Check for unconsumed review debt (per-session)
                debt = None
                try:
                    debt = self.skill_change_store.find_unconsumed_review_debt(
                        key, retry_limit=3,
                    )
                except Exception:
                    debt = None

                # Check for open flow marker (scope expansion)
                open_marker = None
                try:
                    open_marker = self.skill_change_store.find_open_flow_marker(key)
                except Exception:
                    open_marker = None

                if debt is not None and hs.get("active_review_run_id") is None:
                    # Priority 1: Retry the oldest unconsumed debt
                    new_run_id = ""
                    try:
                        new_run_id = self.skill_change_store.create_review_run(
                            session_key=key,
                            trigger_session=key,
                            trigger_type="retry_unconsumed",
                            trigger_reason=f"retry of {debt.id}, attempt={debt.retry_count + 1}",
                            review_epoch=self._hermes_epoch,
                            hermes_enabled=True,
                            iters_since_skill_manage=hs["iters_since_skill_manage"],
                            user_turns_since_review=hs["user_turns_since_review"],
                            reviews_this_session=hs["reviews_this_session"],
                            pending_count=pending,
                            nudge_interval=cfg.hermes_nudge_interval,
                            cooldown_turns=cfg.hermes_cooldown_turns,
                            max_pending=cfg.hermes_max_pending,
                            max_reviews_per_session=cfg.hermes_max_reviews_per_session,
                            distill_enabled=cfg.hermes_distill_snapshot,
                            reject_feedback_enabled=cfg.hermes_use_reject_feedback,
                            replay_of_run_id=debt.id,
                            retry_count=debt.retry_count + 1,
                            trigger_iters=debt.trigger_iters,
                            trigger_user_turns=debt.trigger_user_turns,
                        )
                        self.skill_change_store.mark_review_run_replayed(debt.id, new_run_id)
                    except Exception:
                        new_run_id = ""
                        logger.warning("Hermes: failed to create retry run, marking debt abandoned")
                        try:
                            self.skill_change_store.mark_review_run_abandoned(debt.id, "retry_run_creation_failed")
                        except Exception:
                            pass

                    if new_run_id:
                        if cfg.hermes_distill_snapshot:
                            review_snapshot = self._distill_for_review(session.messages)
                        else:
                            import copy
                            review_snapshot = copy.deepcopy(session.messages)
                        original_msg_count = len(session.messages)
                        original_chars = 0
                        for m in session.messages:
                            c = m.get("content", "")
                            original_chars += len(c) if isinstance(c, str) else len(json.dumps(c))
                        hs["active_review_run_id"] = new_run_id
                        self._schedule_background(self._run_skill_review(
                            review_snapshot,
                            review_epoch=self._hermes_epoch,
                            run_id=new_run_id,
                            original_message_count=original_msg_count,
                            original_chars=original_chars,
                            _consume_on_complete=(debt.trigger_iters, debt.trigger_user_turns),
                        ))
                elif open_marker is not None and hs.get("active_review_run_id") is None and pending < cfg.hermes_max_pending:
                    # Priority 2: Resume partial flow marker
                    scope = self._build_hermes_review_scope(
                        session=session,
                        session_key=key,
                        marker=open_marker,
                    )
                    if scope.status == "partial_deferred":
                        # Still incomplete, update marker
                        self.skill_change_store.create_or_update_flow_marker(
                            session_key=key,
                            module_id=scope.module_id,
                            flow_key=scope.flow_key,
                            start_msg_idx=scope.start_idx,
                            last_seen_msg_idx=len(session.messages) - 1,
                            trigger_msg_idx=scope.trigger_idx,
                            reason=scope.partial_reason or "partial_flow",
                            open_action=scope.open_action,
                        )
                        hs["user_turns_since_review"] += 1
                    else:
                        # Flow completed — create resume review run
                        scope_messages = scope.messages
                        if cfg.hermes_distill_snapshot:
                            review_snapshot = self._distill_for_review(scope_messages)
                        else:
                            import copy
                            review_snapshot = copy.deepcopy(scope_messages)
                        original_msg_count = len(scope_messages)
                        original_chars = 0
                        for m in scope_messages:
                            c = m.get("content", "")
                            original_chars += len(c) if isinstance(c, str) else len(json.dumps(c))

                        run_id = ""
                        try:
                            run_id = self.skill_change_store.create_review_run(
                                session_key=key,
                                trigger_session=key,
                                trigger_type="resume_partial_flow",
                                trigger_reason=f"resume marker {open_marker.id}, module={scope.module_id}",
                                review_epoch=self._hermes_epoch,
                                hermes_enabled=True,
                                iters_since_skill_manage=hs["iters_since_skill_manage"],
                                user_turns_since_review=hs["user_turns_since_review"],
                                reviews_this_session=hs["reviews_this_session"],
                                pending_count=pending,
                                nudge_interval=cfg.hermes_nudge_interval,
                                cooldown_turns=cfg.hermes_cooldown_turns,
                                max_pending=cfg.hermes_max_pending,
                                max_reviews_per_session=cfg.hermes_max_reviews_per_session,
                                distill_enabled=cfg.hermes_distill_snapshot,
                                reject_feedback_enabled=cfg.hermes_use_reject_feedback,
                                metadata={
                                    "scope_status": scope.status,
                                    "scope_start_idx": scope.start_idx,
                                    "scope_end_idx": scope.end_idx,
                                    "module_id": scope.module_id,
                                    "flow_key": scope.flow_key,
                                    "flow_marker_id": scope.marker_id,
                                    "expanded_backward": scope.expanded_backward,
                                    "expanded_forward": scope.expanded_forward,
                                },
                            )
                        except Exception:
                            run_id = ""
                            logger.warning("Hermes: failed to create resume review run")
                        if run_id:
                            self.skill_change_store.mark_flow_marker_reviewed(open_marker.id, run_id)
                        hs["active_review_run_id"] = run_id or None
                        scope_note = (
                            "本次 Hermes review 的原始触发点位于 module_skill_runtime 流程附近，"
                            "系统已按同 module_id 的流程边界进行有限扩展。"
                            "请基于扩展后的完整流程判断是否存在可复用 skill；"
                            "不要记录半截流程状态、一次性路径、临时 action 或未闭环步骤。"
                        ) if scope.status == "expanded_complete" else None
                        self._schedule_background(self._run_skill_review(
                            review_snapshot, review_epoch=self._hermes_epoch,
                            run_id=run_id, original_message_count=original_msg_count,
                            original_chars=original_chars,
                            scope_note=scope_note,
                            _consume_on_complete=(hs["iters_since_skill_manage"], hs["user_turns_since_review"]),
                        ))
                        logger.info(
                            "Hermes: resumed partial module flow | marker={} session={} module={} start={} end={}",
                            open_marker.id, key, scope.module_id, scope.start_idx, scope.end_idx,
                        )
                elif should_trigger:
                    # Priority 3: Normal trigger — check scope before reviewing
                    trigger_iters = hs["iters_since_skill_manage"]
                    trigger_user_turns = hs["user_turns_since_review"]
                    trigger_idx = len(session.messages) - 1

                    scope = self._build_hermes_review_scope(
                        session=session,
                        session_key=key,
                        trigger_idx=trigger_idx,
                    )

                    if scope.status == "partial_deferred":
                        # Defer: create marker and deferred run, but don't start review
                        marker_id = ""
                        try:
                            marker_id = self.skill_change_store.create_or_update_flow_marker(
                                session_key=key,
                                module_id=scope.module_id,
                                flow_key=scope.flow_key,
                                start_msg_idx=scope.start_idx,
                                last_seen_msg_idx=scope.end_idx,
                                trigger_msg_idx=trigger_idx,
                                reason=scope.partial_reason or "partial_flow",
                                open_action=scope.open_action,
                            )
                        except Exception:
                            marker_id = ""

                        run_id = ""
                        try:
                            run_id = self.skill_change_store.create_review_run(
                                session_key=key,
                                trigger_session=key,
                                trigger_type="deferred_partial_flow",
                                trigger_reason=f"partial_flow:{scope.partial_reason}",
                                review_epoch=self._hermes_epoch,
                                hermes_enabled=True,
                                iters_since_skill_manage=trigger_iters,
                                user_turns_since_review=trigger_user_turns,
                                reviews_this_session=hs["reviews_this_session"],
                                pending_count=pending,
                                nudge_interval=cfg.hermes_nudge_interval,
                                cooldown_turns=cfg.hermes_cooldown_turns,
                                max_pending=cfg.hermes_max_pending,
                                max_reviews_per_session=cfg.hermes_max_reviews_per_session,
                                distill_enabled=cfg.hermes_distill_snapshot,
                                reject_feedback_enabled=cfg.hermes_use_reject_feedback,
                                metadata={
                                    "flow_marker_id": marker_id,
                                    "scope_status": scope.status,
                                    "module_id": scope.module_id,
                                    "flow_key": scope.flow_key,
                                    "partial_reason": scope.partial_reason,
                                    "scope_start_idx": scope.start_idx,
                                    "scope_end_idx": scope.end_idx,
                                    "scope_trigger_idx": trigger_idx,
                                },
                                trigger_iters=trigger_iters,
                                trigger_user_turns=trigger_user_turns,
                            )
                        except Exception:
                            run_id = ""
                        if run_id:
                            self.skill_change_store.finish_review_run(
                                run_id,
                                status="deferred_partial_flow",
                                skip_reason=scope.partial_reason or "partial_flow",
                                result_summary_zh="检测到 Hermes 触发点位于未完成的模块流程中，已记录流程起点，等待后续消息补齐后再审核。",
                            )
                        hs["user_turns_since_review"] = 0
                        logger.info(
                            "Hermes: deferred partial module flow | session={} module={} reason={} start={} trigger={} end={}",
                            key, scope.module_id, scope.partial_reason, scope.start_idx, trigger_idx, scope.end_idx,
                        )
                    else:
                        # Complete or expanded_complete — proceed with review
                        scope_messages = scope.messages
                        if cfg.hermes_distill_snapshot:
                            review_snapshot = self._distill_for_review(scope_messages)
                        else:
                            import copy
                            review_snapshot = copy.deepcopy(scope_messages)
                        run_id = ""
                        original_msg_count = len(scope_messages)
                        original_chars = 0
                        try:
                            for m in scope_messages:
                                c = m.get("content", "")
                                original_chars += len(c) if isinstance(c, str) else len(json.dumps(c))
                            run_id = self.skill_change_store.create_review_run(
                                session_key=key,
                                trigger_session=key,
                                trigger_reason=f"nudge={trigger_iters}, pending={pending}, cooldown={trigger_user_turns}, reviews={hs['reviews_this_session']}",
                                review_epoch=self._hermes_epoch,
                                hermes_enabled=True,
                                iters_since_skill_manage=trigger_iters,
                                user_turns_since_review=trigger_user_turns,
                                reviews_this_session=hs["reviews_this_session"],
                                pending_count=pending,
                                nudge_interval=cfg.hermes_nudge_interval,
                                cooldown_turns=cfg.hermes_cooldown_turns,
                                max_pending=cfg.hermes_max_pending,
                                max_reviews_per_session=cfg.hermes_max_reviews_per_session,
                                distill_enabled=cfg.hermes_distill_snapshot,
                                reject_feedback_enabled=cfg.hermes_use_reject_feedback,
                                metadata={
                                    "scope_status": scope.status,
                                    "scope_start_idx": scope.start_idx,
                                    "scope_end_idx": scope.end_idx,
                                    "scope_trigger_idx": trigger_idx,
                                    "module_id": scope.module_id,
                                    "flow_key": scope.flow_key,
                                    "expanded_backward": scope.expanded_backward,
                                    "expanded_forward": scope.expanded_forward,
                                },
                            )
                        except Exception:
                            run_id = ""
                            logger.warning("Hermes: failed to create review run, continuing without tracking")
                        hs["active_review_run_id"] = run_id or None
                        scope_note = (
                            "本次 Hermes review 的原始触发点位于 module_skill_runtime 流程附近，"
                            "系统已按同 module_id 的流程边界进行有限扩展。"
                            "请基于扩展后的完整流程判断是否存在可复用 skill；"
                            "不要记录半截流程状态、一次性路径、临时 action 或未闭环步骤。"
                        ) if scope.status == "expanded_complete" else None
                        self._schedule_background(self._run_skill_review(
                            review_snapshot, review_epoch=self._hermes_epoch,
                            run_id=run_id, original_message_count=original_msg_count,
                            original_chars=original_chars,
                            scope_note=scope_note,
                            _consume_on_complete=(trigger_iters, trigger_user_turns),
                        ))
                else:
                    hs["user_turns_since_review"] += 1

        # Background: expire stale skill change requests
        async def _expire_bg():
            self.skill_change_store.expire_requests()
            self.skill_change_store.cleanup_stale_review_runs(max_running_minutes=30)
            max_age = getattr(cfg, "hermes_partial_flow_max_age_hours", 24) if self._skills_auto_config else 24
            self.skill_change_store.cleanup_stale_flow_markers(max_age_hours=max_age)
        self._schedule_background(_expire_bg())

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

        meta = dict(msg.metadata or {})
        if on_stream is not None:
            meta["_streamed"] = True
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=meta,
        )

    @staticmethod
    def _image_placeholder(block: dict[str, Any]) -> dict[str, str]:
        """Convert an inline image block into a compact text placeholder."""
        path = (block.get("_meta") or {}).get("path", "")
        return {"type": "text", "text": f"[image: {path}]" if path else "[image]"}

    def _sanitize_persisted_blocks(
        self,
        content: list[dict[str, Any]],
        *,
        truncate_text: bool = False,
        drop_runtime: bool = False,
    ) -> list[dict[str, Any]]:
        """Strip volatile multimodal payloads before writing session history."""
        filtered: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                filtered.append(block)
                continue

            if (
                drop_runtime
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
                and block["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG)
            ):
                continue

            if (
                block.get("type") == "image_url"
                and block.get("image_url", {}).get("url", "").startswith("data:image/")
            ):
                filtered.append(self._image_placeholder(block))
                continue

            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text = block["text"]
                if truncate_text and len(text) > self._TOOL_RESULT_MAX_CHARS:
                    text = text[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
                filtered.append({**block, "text": text})
                continue

            filtered.append(block)

        return filtered

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool":
                if isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                    entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
                elif isinstance(content, list):
                    filtered = self._sanitize_persisted_blocks(content, truncate_text=True)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    # Strip the runtime-context prefix, keep only the user text.
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
                if isinstance(content, list):
                    filtered = self._sanitize_persisted_blocks(content, drop_runtime=True)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _run_skill_review(self, messages_snapshot: list[dict], *, review_epoch: int | None = None,
                                   run_id: str = "", original_message_count: int = 0,
                                   original_chars: int = 0,
                                   scope_note: str | None = None,
                                   _consume_on_complete: tuple[int, int] | None = None) -> None:
        """Background Hermes skill review: analyze conversation and create/update skills."""
        # Stale-write guard: if Hermes was disabled or config changed after this
        # review was scheduled, abort without writing anything.
        if not self._skills_auto_config or not self._skills_auto_config.hermes_enabled:
            logger.info("Hermes: skipping in-flight review — Hermes disabled at runtime")
            if run_id:
                self.skill_change_store.finish_review_run(run_id, status="disabled", skip_reason="hermes_disabled")
            self._clear_active_review(run_id)
            return
        if review_epoch is not None and review_epoch != self._hermes_epoch:
            logger.info("Hermes: skipping in-flight review — epoch mismatch (config changed)")
            if run_id:
                self.skill_change_store.finish_review_run(run_id, status="cancelled_by_epoch", skip_reason="epoch_mismatch")
            self._clear_active_review(run_id)
            return

        if run_id:
            self.skill_change_store.mark_review_run_running(run_id)

        _SKILL_REVIEW_PROMPT = (
            "Review the conversation above and consider whether a new skill should be created.\n\n"
            "Work in this order — do not skip steps:\n\n"
            "1. SURVEY existing skills. Call list_dir on the workspace skills directory.\n"
            "   If anything looks relevant, read_file its SKILL.md.\n"
            "2. THINK CLASS-FIRST. What general pattern of task did the user complete?\n"
            "   What conditions will trigger this pattern again?\n"
            "3. If an existing skill already covers this pattern, do NOT create a new one.\n"
            "4. If the pattern is genuinely new and no existing skill covers it,\n"
            "   use skill_manage(action='create') with a class-level name.\n\n"
            "IMPORTANT — Hermes may ONLY propose CREATE requests for new skills.\n"
            "Do NOT patch, edit, or delete existing skills.\n\n"
            "Only act when something is genuinely worth saving.\n"
            "If nothing stands out, just say 'Nothing to save.' and stop.\n\n"
            "DO NOT create a skill if:\n"
            "- The task is one-time (e.g., fixing a specific typo or a single bug).\n"
            "- The conversation is mostly Q&A or exploration, not a repeatable workflow.\n"
            "- There was no multi-step tool usage or user correction pattern.\n"
            "- The pattern is already fully covered by an existing skill.\n"
            "- You cannot state a concrete future trigger (when this skill should activate again).\n"
            "- You cannot explain why this is reusable rather than session-only.\n"
            "- The proposed change only records a temporary token, branch name, path, or command.\n"
            "- The task is environment-specific and will not generalize.\n"
            "- An existing skill is related but distinct — only create when the reusable class is genuinely separate."
        )

        # Build a minimal tool registry for the review agent
        from nanobot.agent.tools.skill_manage import SkillManageTool
        from nanobot.agent.tools.filesystem import ReadFileTool, ListDirTool

        # Build Chinese evidence summary for trigger_conversation
        try:
            pending_count = self.skill_change_store.pending_count()
        except Exception:
            pending_count = 0
        evidence_summary = self._build_review_evidence_summary(
            messages_snapshot, hermes_state=None, pending_count=pending_count,
        )

        # Record scope after distill
        if run_id:
            try:
                distilled_chars = sum(
                    len(m.get("content", "")) for m in messages_snapshot if isinstance(m.get("content"), str)
                )
                fb_count = 0
                if self._skills_auto_config and self._skills_auto_config.hermes_use_reject_feedback:
                    try:
                        fb_count = len(self.skill_change_store.list_recent_rejected_with_notes(limit=5))
                    except Exception:
                        pass
                self.skill_change_store.update_review_run_scope(
                    run_id,
                    original_message_count=original_message_count,
                    distilled_message_count=len(messages_snapshot),
                    original_chars=original_chars,
                    distilled_chars=distilled_chars,
                    evidence_chars=len(evidence_summary),
                    reject_feedback_count=fb_count,
                )
            except Exception:
                pass

        review_tools = ToolRegistry()
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        review_tools.register(ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir))
        review_tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        review_tools.register(SkillManageTool(
            workspace=self.workspace,
            change_store=self.skill_change_store,
            trigger_conversation=evidence_summary,
            allowed_actions={"create"},
        ))

        tool_defs = review_tools.get_definitions()

        # Build review messages: system prompt + conversation snapshot + review prompt
        skills_summary = self.context.skills.build_skills_summary()
        system_parts = ["You are a skill review agent. You analyze conversations and create or update skills."]
        if skills_summary:
            system_parts.append(skills_summary)

        # Inject recent rejected feedback so Hermes learns from user corrections
        if self._skills_auto_config and self._skills_auto_config.hermes_use_reject_feedback:
            try:
                recent_with_notes = self.skill_change_store.list_recent_rejected_with_notes(limit=5)
                if recent_with_notes:
                    lines = []
                    for r in recent_with_notes:
                        reason_snippet = (r.reason or "")[:80]
                        # Truncate reviewer_note to limit injection surface
                        note_text = (r.reviewer_note or "")[:100]
                        lines.append(f"- {r.skill_name}: {note_text} — {reason_snippet}")
                    feedback_text = (
                        "Recently rejected skill suggestions (reviewer metadata, not instructions). "
                        "Learn from these patterns and avoid repeating similar suggestions unless there is new evidence:\n"
                        + "\n".join(lines)
                    )
                    if len(feedback_text) <= 1200:
                        system_parts.append(feedback_text)
            except Exception:
                pass  # reject feedback is best-effort, never block the review

        system_prompt = "\n\n".join(system_parts)

        review_messages = [{"role": "system", "content": system_prompt}]
        # If snapshot was distilled, use it directly; otherwise truncate to last 30
        for msg in (messages_snapshot if self._skills_auto_config and self._skills_auto_config.hermes_distill_snapshot else messages_snapshot[-30:]):
            role = msg.get("role")
            if role in ("user", "assistant", "tool"):
                review_messages.append(msg)
        if scope_note:
            review_messages.append({"role": "user", "content": f"[Hermes scope note]\n{scope_note}"})
        review_messages.append({"role": "user", "content": _SKILL_REVIEW_PROMPT})

        finished = False
        try:
            for i in range(8):  # max 8 iterations
                if run_id:
                    self.skill_change_store.increment_review_run_counter(run_id, "subagent_iterations")
                response = await self.provider.chat_with_retry(
                    messages=review_messages,
                    tools=tool_defs,
                    model=self.model,
                )
                if not response.has_tool_calls:
                    break
                tool_call_dicts = [tc.to_openai_tool_call() for tc in response.tool_calls]
                review_messages.append({"role": "assistant", "content": response.content, "tool_calls": tool_call_dicts})
                for tc in response.tool_calls:
                    if run_id:
                        self.skill_change_store.increment_review_run_counter(run_id, "subagent_tool_calls")
                    try:
                        result = await review_tools.execute(tc.name, tc.arguments)
                        if isinstance(result, dict):
                            result = json.dumps(result, ensure_ascii=False)
                    except Exception as e:
                        result = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
                    # Track skill_manage outcomes
                    if run_id and tc.name == "skill_manage":
                        self.skill_change_store.increment_review_run_counter(run_id, "skill_manage_calls")
                        try:
                            data = json.loads(result) if isinstance(result, str) else result
                            status_val = data.get("status", "") if isinstance(data, dict) else ""
                            _status_counter = {
                                "pending_review": "requests_created",
                                "merged_with_existing": "requests_merged",
                                "blocked_by_blacklist": "requests_blocked",
                                "covered_by_existing": "requests_covered",
                            }
                            if status_val in _status_counter:
                                self.skill_change_store.increment_review_run_counter(run_id, _status_counter[status_val])
                            if isinstance(data, dict) and data.get("related_existing_skill_ids"):
                                self.skill_change_store.increment_review_run_counter(run_id, "requests_related")
                        except Exception:
                            pass
                    review_messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result})

            # Extract and log any successful actions
            summary_parts: list[str] = []
            for msg in review_messages:
                if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
                    try:
                        data = json.loads(msg["content"])
                        if isinstance(data, dict) and data.get("success"):
                            logger.info("Hermes skill review: {}", data.get("message", "action completed"))
                            summary_parts.append(data.get("message", "")[:100])
                    except (json.JSONDecodeError, TypeError):
                        pass
            # Normal completion — consumed
            if run_id:
                summary_zh = "; ".join(summary_parts[:3]) if summary_parts else "审核完成"
                self.skill_change_store.finish_review_run(run_id, status="completed", result_summary_zh=summary_zh)
                self.skill_change_store.mark_review_run_consumed(run_id)
            finished = True
            if _consume_on_complete and run_id:
                self._consume_review_trigger(run_id, _consume_on_complete)
        except asyncio.CancelledError:
            if run_id and not finished:
                self.skill_change_store.finish_review_run(run_id, status="interrupted", skip_reason="task_cancelled")
            raise
        except Exception as e:
            logger.warning("Hermes skill review failed: {}", e)
            if run_id and not finished:
                self.skill_change_store.finish_review_run(run_id, status="failed", error_message=str(e)[:500])
        finally:
            if run_id and not finished:
                try:
                    self.skill_change_store.finish_review_run(run_id, status="interrupted", skip_reason="unexpected_exit")
                except Exception:
                    pass
            self._clear_active_review(run_id)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        model_name: str | None = None,
    ) -> OutboundMessage | None:
        """Process a message directly and return the outbound payload."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        return await self._process_message(
            msg, session_key=session_key, on_progress=on_progress,
            on_stream=on_stream, on_stream_end=on_stream_end,
            model_name=model_name,
        )
