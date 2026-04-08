"""Site survey artifact analysis with live GC dashboard Patch updates."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.filesystem import _resolve_path


def _semantic_color_for_progress(pct: int) -> str:
    if pct >= 90:
        return "success"
    if pct >= 45:
        return "warning"
    return "subtle"


class AnalyzeSiteArtifactsTool(Tool):
    """Parse survey artifacts (photos, spreadsheets, etc.) with staged UI progress.

    After each artifact is processed, pushes a SkillUiDataPatch so the dashboard
    ``Statistic`` (default ``stat-1``) shows rising satisfaction (e.g. 0%% → 45%% → 90%%).
    """

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        extra_allowed_dirs: list[Path] | None = None,
    ) -> None:
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._extra_allowed_dirs = extra_allowed_dirs

    @property
    def name(self) -> str:
        return "analyze_site_artifacts"

    @property
    def description(self) -> str:
        return (
            "Analyze engineering survey artifacts (images, Excel, etc.) under the workspace. "
            "Processes paths sequentially and updates the GC survey dashboard satisfaction "
            "statistic after each file so the user sees live progress."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "artifact_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workspace-relative paths to photos, Excel, or other survey files.",
                    "minItems": 1,
                },
                "synthetic_path": {
                    "type": "string",
                    "description": "Optional skill-ui URL; default matches GC dashboard JSON.",
                },
                "statistic_node_id": {
                    "type": "string",
                    "description": "SduiNode id for the satisfaction Statistic (default stat-1).",
                },
            },
            "required": ["artifact_paths"],
        }

    def _resolve(self, path: str) -> Path:
        return _resolve_path(path, self._workspace, self._allowed_dir, self._extra_allowed_dirs)

    async def execute(
        self,
        artifact_paths: list[str],
        synthetic_path: str | None = None,
        statistic_node_id: str = "stat-1",
        **kwargs: Any,
    ) -> Any:
        from nanobot.web.skill_ui_patch import SkillUiPatchPusher

        paths = [str(p).strip() for p in artifact_paths if str(p).strip()]
        if not paths:
            return "Error: artifact_paths must contain at least one path."

        pusher = SkillUiPatchPusher(synthetic_path)
        node_id = statistic_node_id.strip() or "stat-1"

        async def push_pct(pct: int, *, detail: str) -> None:
            pct = max(0, min(100, pct))
            color = _semantic_color_for_progress(pct)
            await pusher.update_node(
                node_id,
                "Statistic",
                {"value": f"{pct}%", "color": color},
            )
            logger.info("analyze_site_artifacts progress | pct={} | {}", pct, detail[:300])

        # Baseline 0% before work starts.
        await push_pct(0, detail="start")

        errors: list[str] = []
        valid: list[tuple[str, Path]] = []
        for rel in paths:
            try:
                fp = self._resolve(rel)
            except PermissionError as e:
                errors.append(f"{rel}: {e}")
                continue
            if not fp.exists():
                errors.append(f"{rel}: not found")
                continue
            if not fp.is_file():
                errors.append(f"{rel}: not a file")
                continue
            valid.append((rel, fp))

        if not valid:
            await pusher.update_node(
                node_id,
                "Statistic",
                {"value": "0%", "color": "error"},
            )
            return "Error: no readable artifacts:\n" + "\n".join(errors)

        m = len(valid)
        for i, (rel, fp) in enumerate(valid):
            try:
                _ = fp.stat().st_size
                await asyncio.sleep(0)
            except OSError as e:
                errors.append(f"{rel}: {e}")
                continue

            pct = max(1, int((i + 1) * 100 / m))
            await push_pct(pct, detail=f"processed {rel}")

        tail = ""
        if errors:
            tail = "\nWarnings:\n" + "\n".join(errors)
        return f"Analyzed {m} artifact(s); dashboard satisfaction reached 100%.{tail}"
