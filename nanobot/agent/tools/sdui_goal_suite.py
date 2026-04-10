"""SDUI v3 Goal Suite verification tools.

These tools are deterministic and meant for internal QA:
- Open a known dashboard (workspace skill data file) and stream patches
- Append DataGrid rows with isPartial then stabilize
- Emit ChatCard with FilePicker + intent button, then replace the card
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.web.mission_control import MissionControlManager
from nanobot.web.skill_ui_patch import build_append_op, build_skill_ui_data_patch_payload


GOAL_SUITE_DATAFILE = "workspace/skills/sdui-goal-suite/data/dashboard.json"
GOAL_SUITE_SYNTHETIC_PATH = f"skill-ui://SduiView?dataFile={GOAL_SUITE_DATAFILE}"
GOAL_SUITE_DOC_ID = "suite:goal"


class RunSduiGoalSuiteTool(Tool):
    @property
    def name(self) -> str:
        return "run_sdui_goal_suite"

    @property
    def description(self) -> str:
        return "Run SDUI v3 goal suite: stream patches, append rows, emit ChatCard and replace it."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Current threadId (for chat cards docId)"},
                "synthetic_path": {"type": "string", "description": "Override skill-ui synthetic path"},
                "doc_id": {"type": "string", "description": "Override docId"},
            },
            "required": ["thread_id"],
        }

    async def execute(
        self,
        thread_id: str,
        synthetic_path: str | None = None,
        doc_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        from nanobot.agent.loop import emit_skill_ui_data_patch_event  # lazy: avoid circular import

        sp = (synthetic_path or "").strip() or GOAL_SUITE_SYNTHETIC_PATH
        did = (doc_id or "").strip() or GOAL_SUITE_DOC_ID

        # 1) Stream partial rows into DataGrid
        for i in range(3):
            row = {
                "kind": "html" if i == 2 else ("xlsx" if i == 1 else "docx"),
                "name": f"产物 {i + 1}",
                "preview": f"[AUTO_OPEN](browser://http://example.local/artifact/{i + 1})",
            }
            payload = await build_skill_ui_data_patch_payload(
                synthetic_path=sp,
                doc_id=did,
                is_partial=True,
                ops=[build_append_op(node_id="artifact-grid", field="rows", value=[row])],
            )
            await emit_skill_ui_data_patch_event(payload)
            await asyncio.sleep(0.25)

        # stable patch: clear partial
        stable = await build_skill_ui_data_patch_payload(
            synthetic_path=sp,
            doc_id=did,
            is_partial=False,
            ops=[],
        )
        await emit_skill_ui_data_patch_event(stable)

        # 2) Emit a chat card with FilePicker + intent button (replace-driven state machine)
        mc = MissionControlManager(thread_id=thread_id, docman=None)
        handle = await mc.ask_for_file(
            purpose="goalSuiteUpload",
            title="Goal Suite：请上传说明文件",
            accept=".pdf,.doc,.docx,.md,.txt,image/*",
        )
        await mc.replace_card(
            card_id=handle.card_id,
            title="Goal Suite：请上传说明文件",
            node={
                "type": "Stack",
                "gap": "md",
                "children": [
                    {
                        "type": "FilePicker",
                        "purpose": "goalSuiteUpload",
                        "accept": ".pdf,.doc,.docx,.md,.txt,image/*",
                        "label": "上传说明文件",
                        "helpText": "上传成功后会写入 chat:<threadId> 的 meta.uiState.uploads。",
                    },
                    {
                        "type": "Button",
                        "label": "模拟完成上传",
                        "variant": "secondary",
                        "color": "accent",
                        "action": {"kind": "chat_card_intent", "verb": "complete_upload", "cardId": handle.card_id},
                    },
                ],
            },
            doc_id=handle.doc_id,
        )

        return {
            "ok": True,
            "syntheticPath": sp,
            "docId": did,
            "chatCardId": handle.card_id,
            "chatDocId": handle.doc_id,
            "openUi": f"skill-ui://SduiView?dataFile={GOAL_SUITE_DATAFILE}",
        }

