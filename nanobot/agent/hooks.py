"""Pre/Post Compact hook runner for context management."""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass, field

from loguru import logger

from nanobot.config.schema import HooksConfig, HookConfig


@dataclass
class PreCompactResult:
    proceed: bool = True
    extra_instructions: str = ""


class HookRunner:
    """Executes shell commands as compact lifecycle hooks."""

    def __init__(self, hooks_config: HooksConfig | None = None):
        cfg = hooks_config or HooksConfig()
        self.pre_hooks = cfg.pre_compact
        self.post_hooks = cfg.post_compact

    async def run_pre_compact(self, trigger: str, context: dict) -> PreCompactResult:
        """Run all pre-compact hooks. Returns aggregated result."""
        instructions: list[str] = []
        for hook in self.pre_hooks:
            if trigger not in hook.trigger:
                continue
            try:
                result = await self._run_hook(hook, context)
                if result is None:
                    # exit code 2 → abort
                    return PreCompactResult(proceed=False, extra_instructions="")
                instructions.append(result)
            except Exception as e:
                logger.warning("PreCompact hook failed: {}", e)
        return PreCompactResult(
            proceed=True,
            extra_instructions="\n".join(instructions),
        )

    async def run_post_compact(self, trigger: str, context: dict) -> None:
        """Run all post-compact hooks. Fire-and-forget style."""
        for hook in self.post_hooks:
            if trigger not in hook.trigger:
                continue
            try:
                await self._run_hook(hook, context)
            except Exception as e:
                logger.warning("PostCompact hook failed: {}", e)

    @staticmethod
    async def _run_hook(hook: HookConfig, context: dict) -> str | None:
        """Execute a single hook command.

        Returns stdout text on success (exit 0), None on abort (exit 2).
        Raises on timeout or subprocess errors.
        """
        proc = await asyncio.create_subprocess_exec(
            *shlex.split(hook.command),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=json.dumps(context).encode()),
            timeout=hook.timeout,
        )
        if proc.returncode == 2:
            return None  # abort signal
        if proc.returncode != 0:
            logger.warning(
                "Hook '{}' exited with code {}: {}",
                hook.command,
                proc.returncode,
                stderr.decode(errors="replace")[:200],
            )
        if proc.returncode == 0 and stdout:
            return stdout.decode(errors="replace").strip()
        return ""
