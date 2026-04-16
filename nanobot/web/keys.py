"""Typed aiohttp application keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp.web_app import AppKey

from nanobot.web.remote_center import RemoteCenterClient, RemoteCenterSessionStore
from nanobot.web.run_registry import ApprovalRegistry, RunRegistry

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.config.schema import Config
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from collections.abc import Awaitable, Callable
    from typing import Any

RUN_REGISTRY_KEY: AppKey[RunRegistry] = AppKey("nanobot_run_registry")
APPROVAL_REGISTRY_KEY: AppKey[ApprovalRegistry] = AppKey("nanobot_approval_registry")
AGENT_LOOP_KEY: AppKey[AgentLoop | None] = AppKey("nanobot_agent_loop")
CONFIG_KEY: AppKey[Config | None] = AppKey("nanobot_config")
REMOTE_CENTER_SESSION_STORE_KEY: AppKey[RemoteCenterSessionStore] = AppKey("nanobot_remote_center_store")
REMOTE_CENTER_CLIENT_FACTORY_KEY: AppKey[type[RemoteCenterClient]] = AppKey("nanobot_remote_center_client_factory")
PENDING_HITL_STORE_KEY: AppKey["PendingHitlStore"] = AppKey("nanobot_pending_hitl_store")
SKILL_RESUME_RUNNER_KEY: AppKey["Callable[..., Awaitable[Any]] | None"] = AppKey("nanobot_skill_resume_runner")
