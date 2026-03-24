"""Typed aiohttp application keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp.web_app import AppKey

from nanobot.web.run_registry import RunRegistry

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.config.schema import Config

RUN_REGISTRY_KEY: AppKey[RunRegistry] = AppKey("nanobot_run_registry")
AGENT_LOOP_KEY: AppKey[AgentLoop | None] = AppKey("nanobot_agent_loop")
CONFIG_KEY: AppKey[Config | None] = AppKey("nanobot_config")
