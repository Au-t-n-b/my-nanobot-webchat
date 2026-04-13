"""Agent tool: 统一模块 Skill 运行时（大盘 Patch + HITL ChatCard）。"""

from __future__ import annotations

import json
from typing import Any

from nanobot.agent.tools.base import Tool


class ModuleSkillRuntimeTool(Tool):
    """按 ``<skills_root>/<module_id>/module.json`` 驱动标准流程。"""

    @property
    def name(self) -> str:
        return "module_skill_runtime"

    @property
    def description(self) -> str:
        return (
            "运行已安装的模块 Skill：更新中间栏 Skill-UI 大盘（SkillUiDataPatch），"
            "并在会话中下发引导 / 选择 / 真实文件上传（FilePicker，可拖拽）等 ChatCard。"
            "module_id 为技能目录名；action 依模块 flow（如 demo_compliance：guide/start/choose_standard/upload_material/finish；"
            "module_boilerplate：guide/start/choose_strategy/upload_evidence/after_upload/finish；"
            "simulation_workflow：guide/upload_bundle/upload_bundle_complete/device_confirm/create_device/topo_confirm/finish）。"
            "上传步骤必须由本工具的真实上传 action 触发（如 module_boilerplate 的 upload_evidence、"
            "simulation_workflow 的 upload_bundle，或 demo 的 upload_material），"
            "禁止用 present_choices 模拟上传。"
            "state 可含 standard（策略 id）、upload 等。仅 Web 聊天上下文可用（需 thread_id）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "module_id": {"type": "string", "description": "技能目录名，例如 module_skill_demo"},
                "action": {"type": "string", "description": "流程动作名"},
                "state": {
                    "type": "object",
                    "description": "可选状态补丁（会与同会话内的 HITL 状态合并）",
                },
            },
            "required": ["module_id", "action"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        from nanobot.agent.loop import get_current_thread_id
        from nanobot.web.module_skill_runtime import run_module_action

        module_id = str(kwargs.get("module_id") or "").strip()
        action = str(kwargs.get("action") or "").strip()
        raw_state = kwargs.get("state")
        state = dict(raw_state) if isinstance(raw_state, dict) else {}
        tid = get_current_thread_id()
        result = await run_module_action(
            module_id=module_id,
            action=action,
            state=state,
            thread_id=tid,
            docman=None,
        )
        return json.dumps(result, ensure_ascii=False)
