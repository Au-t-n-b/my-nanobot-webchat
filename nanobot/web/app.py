"""aiohttp Application factory for AGUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from nanobot.web.keys import AGENT_LOOP_KEY, CONFIG_KEY, RUN_REGISTRY_KEY
from nanobot.web.routes import cors_middleware, setup_routes
from nanobot.web.run_registry import RunRegistry

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.config.schema import Config


async def _agui_cleanup(app: web.Application) -> None:
    agent = app[AGENT_LOOP_KEY]
    if agent is not None:
        await agent.close_mcp()


def create_app(
    *,
    agent_loop: AgentLoop | None = None,
    config: Config | None = None,
    run_registry: RunRegistry | None = None,
) -> web.Application:
    """Build AGUI app. ``agent_loop=None`` serves fake SSE (tests / ``--fake``)."""
    app = web.Application(middlewares=[cors_middleware])
    app[AGENT_LOOP_KEY] = agent_loop
    app[CONFIG_KEY] = config
    app[RUN_REGISTRY_KEY] = run_registry or RunRegistry()
    app.on_cleanup.append(_agui_cleanup)
    setup_routes(app)
    return app
