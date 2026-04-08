"""E2E test tool for SDUI v3 M1 — Asset Live Scan (scan-progress / scan-status / DonutChart)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool

# Must match right-panel skill-ui URL and Patch doc bucket (revision is auto-assigned).
# Use workspace-root `test-scan.json` (not `workspace/test-scan.json`): GET /api/file resolves
# `dataFile` relative to workspace; a nested `workspace/` segment is a *subfolder*, and agents
# often write `test-scan.json` at root — mismatches cause {"detail":"File not found"} in Preview.
SCAN_SYNTHETIC_PATH = "skill-ui://SduiView?dataFile=test-scan.json"
SCAN_DOC_ID = "test:scan"
SCAN_DATAFILE_REL = "test-scan.json"


def _baseline_sdui_document() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "type": "SduiDocument",
        "root": {
            "type": "Stack",
            "gap": "lg",
            "children": [
                {
                    "type": "Text",
                    "variant": "title",
                    "content": "机房资产实时扫描 (Asset Live Scan)",
                },
                {
                    "type": "Row",
                    "gap": "md",
                    "children": [
                        {
                            "type": "Statistic",
                            "id": "scan-progress",
                            "title": "总进度",
                            "value": "0%",
                            "color": "accent",
                        },
                        {
                            "type": "Badge",
                            "id": "scan-status",
                            "label": "扫描: 就绪",
                            "color": "subtle",
                            "size": "md",
                        },
                    ],
                },
                {
                    "type": "DonutChart",
                    "id": "scan-donut",
                    "centerLabel": "资产分布",
                    "centerValue": "—",
                    "segments": [
                        {"label": "在线", "value": 40, "color": "success"},
                        {"label": "待确认", "value": 35, "color": "warning"},
                        {"label": "离线", "value": 25, "color": "error"},
                    ],
                },
            ],
        },
    }


def _final_sdui_document() -> dict[str, Any]:
    """Matches the last SkillUiDataPatch batch so ``test-scan.json`` on disk is not left at baseline (0%)."""
    return {
        "schemaVersion": 1,
        "type": "SduiDocument",
        "root": {
            "type": "Stack",
            "gap": "lg",
            "children": [
                {
                    "type": "Text",
                    "variant": "title",
                    "content": "机房资产实时扫描 (Asset Live Scan)",
                },
                {
                    "type": "Row",
                    "gap": "md",
                    "children": [
                        {
                            "type": "Statistic",
                            "id": "scan-progress",
                            "title": "总进度",
                            "value": "100%",
                            "color": "success",
                        },
                        {
                            "type": "Badge",
                            "id": "scan-status",
                            "label": "扫描: 已完成",
                            "color": "success",
                            "size": "md",
                        },
                    ],
                },
                {
                    "type": "DonutChart",
                    "id": "scan-donut",
                    "centerLabel": "资产分布",
                    "centerValue": "100%",
                    "segments": [
                        {"label": "在线", "value": 72, "color": "success"},
                        {"label": "待确认", "value": 18, "color": "warning"},
                        {"label": "离线", "value": 10, "color": "error"},
                    ],
                },
            ],
        },
    }


class RunAssetScanTool(Tool):
    """Writes baseline ``test-scan.json``, then emits 5 SkillUiDataPatch events (1s apart)."""

    def __init__(self, workspace: Path | None = None) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "run_asset_scan"

    @property
    def description(self) -> str:
        return (
            "SDUI v3 M1 E2E: write Asset Live Scan dashboard JSON, then simulate a 5-step scan "
            "with live patches (progress %, status badge, donut). Open the skill-ui URL in the host."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "delay_seconds": {
                    "type": "number",
                    "description": "Seconds between patch steps (default 1.0).",
                },
            },
        }

    def _datafile_path(self) -> Path:
        if self._workspace is None:
            raise RuntimeError("workspace not set")
        return (self._workspace / SCAN_DATAFILE_REL).resolve()

    async def execute(self, delay_seconds: float = 1.0, **kwargs: Any) -> Any:
        from nanobot.web.skill_ui_patch import SkillUiPatchPusher, push_gc_dashboard_node_merge

        if self._workspace is None:
            return "Error: RunAssetScanTool requires workspace."

        delay = float(delay_seconds) if delay_seconds is not None else 1.0
        if delay < 0:
            delay = 0.0

        doc = _baseline_sdui_document()
        out = self._datafile_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("run_asset_scan: wrote baseline | path={}", out)

        pusher = SkillUiPatchPusher(SCAN_SYNTHETIC_PATH, doc_id=SCAN_DOC_ID)

        # Five scan intervals; six SkillUiDataPatch emissions (step 2 uses push_gc + Badge emit; step 6 uses push_gc + batch).
        await asyncio.sleep(delay)
        await pusher.update_nodes(
            [
                ("scan-progress", "Statistic", {"value": "20%", "color": "subtle"}),
                ("scan-status", "Badge", {"label": "扫描: 机柜 PDU-01", "color": "accent"}),
            ]
        )

        await asyncio.sleep(delay)
        await push_gc_dashboard_node_merge(
            "scan-progress",
            "Statistic",
            {"value": "40%", "color": "warning"},
            synthetic_path=SCAN_SYNTHETIC_PATH,
            doc_id=SCAN_DOC_ID,
        )
        await pusher.update_node(
            "scan-status",
            "Badge",
            {"label": "扫描: 核心交换机-01", "color": "accent"},
        )

        await asyncio.sleep(delay)
        await pusher.update_nodes(
            [
                ("scan-progress", "Statistic", {"value": "60%", "color": "warning"}),
                ("scan-status", "Badge", {"label": "扫描: 接入交换机-A3", "color": "accent"}),
                (
                    "scan-donut",
                    "DonutChart",
                    {
                        "centerValue": "60%",
                        "segments": [
                            {"label": "在线", "value": 52, "color": "success"},
                            {"label": "待确认", "value": 33, "color": "warning"},
                            {"label": "离线", "value": 15, "color": "error"},
                        ],
                    },
                ),
            ]
        )

        await asyncio.sleep(delay)
        await pusher.update_nodes(
            [
                ("scan-progress", "Statistic", {"value": "80%", "color": "accent"}),
                ("scan-status", "Badge", {"label": "扫描: 存储阵列-S2", "color": "accent"}),
            ]
        )

        await asyncio.sleep(delay)
        await push_gc_dashboard_node_merge(
            "scan-progress",
            "Statistic",
            {"value": "100%", "color": "success"},
            synthetic_path=SCAN_SYNTHETIC_PATH,
            doc_id=SCAN_DOC_ID,
        )
        await pusher.update_nodes(
            [
                ("scan-status", "Badge", {"label": "扫描: 已完成", "color": "success"}),
                (
                    "scan-donut",
                    "DonutChart",
                    {
                        "centerValue": "100%",
                        "segments": [
                            {"label": "在线", "value": 72, "color": "success"},
                            {"label": "待确认", "value": 18, "color": "warning"},
                            {"label": "离线", "value": 10, "color": "error"},
                        ],
                    },
                ),
            ]
        )

        # Persist final merged view so GET /api/file and any post-run reload are not stuck at baseline.
        out.write_text(
            json.dumps(_final_sdui_document(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("run_asset_scan: wrote final document | path={}", out)

        ui_line = f"[RENDER_UI]({SCAN_SYNTHETIC_PATH})"
        return (
            "SDUI v3 M1 E2E「机房资产实时扫描」已执行：\n"
            f"- 基线文档已写入: `{SCAN_DATAFILE_REL}`\n"
            f"- 已写入基线并推送 **6** 次 SkillUiDataPatch（docId=`{SCAN_DOC_ID}`，revision 递增；其中 **2** 次使用 `push_gc_dashboard_node_merge`）。\n"
            f"- 请在宿主打开：{ui_line}\n"
            "若右栏已挂载同一 `syntheticPath`，应看到进度与状态逐步更新。"
        )
