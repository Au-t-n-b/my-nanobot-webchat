"""Agent tool: single SkillUiChatCard for fault log + symptom intake (SDUI Tabs + deferred upload + confirm)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.user_upload import AGENT_HITL_SKILL_NAME, AGENT_UPLOAD_RESUME_ACTION

SYMPTOM_INPUT_ID = "fault_intake_symptom"
FILE_PURPOSE = "fault_log_intake"


def build_fault_log_intake_node(*, skill_name: str, hitl_request_id: str, save_relative_dir: str) -> dict[str, Any]:
    """SDUI node tree: Stack → Markdown + Tabs(FilePicker defer + TextArea) + ConfirmCard aggregate."""
    return {
        "type": "Stack",
        "gap": "md",
        "children": [
            {
                "type": "Markdown",
                "content": "已为您拉起 **故障诊断** 引擎。为了进行精准诊断，请在下方提供日志或故障现象：",
            },
            {
                "type": "Tabs",
                "id": "fault-intake-tabs",
                "defaultTabId": "tab-log",
                "tabs": [
                    {
                        "id": "tab-log",
                        "label": "提供故障日志",
                        "icon": "fileText",
                        "children": [
                            {
                                "type": "FilePicker",
                                "id": "fault-intake-files",
                                "purpose": FILE_PURPOSE,
                                "accept": ".log,.txt,.json,.zip,.md",
                                "multiple": True,
                                "helpText": "上传完成后可切换到「描述问题现象」填写说明；最后点击下方「确认并启动诊断」一次提交。",
                                "skillName": skill_name,
                                "hitlRequestId": hitl_request_id,
                                "deferHitlSubmit": True,
                                "saveRelativeDir": save_relative_dir,
                            },
                        ],
                    },
                    {
                        "id": "tab-symptom",
                        "label": "描述问题现象",
                        "icon": "terminal",
                        "children": [
                            {
                                "type": "TextArea",
                                "inputId": SYMPTOM_INPUT_ID,
                                "placeholder": "在此粘贴报错日志、Exception 堆栈…",
                                "rows": 8,
                            },
                        ],
                    },
                ],
            },
            {
                "type": "ConfirmCard",
                "id": "fault-intake-confirm",
                "title": "将提交已上传日志（如有）与现象描述，并启动诊断。",
                "confirmLabel": "确认并启动诊断",
                "cancelLabel": "暂不启动",
                "skillName": skill_name,
                "hitlRequestId": hitl_request_id,
                "aggregateDeferredUploads": True,
                "aggregateTextInputIds": [SYMPTOM_INPUT_ID],
            },
        ],
    }


class PresentFaultLogIntakeCardTool(Tool):
    """Emit one chat card (图二) with deferred file upload + TextArea + single Confirm submit."""

    @property
    def name(self) -> str:
        return "present_fault_log_intake_card"

    @property
    def description(self) -> str:
        return (
            "Present a single chat card for fault diagnosis intake: tabs for log file upload and symptom text, "
            "then one confirm button to submit both to the pending HITL request (nanobot_agent / agent_upload)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "save_relative_dir": {
                    "type": "string",
                    "description": "Workspace-relative directory for uploaded logs (default: uploads/temp).",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> Any:
        from nanobot.agent.loop import get_chat_docman, get_current_thread_id, get_pending_hitl_store
        from nanobot.web.mission_control import MissionControlManager

        thread_id = (get_current_thread_id() or "").strip()
        store = get_pending_hitl_store()
        tool_call_id = str(kwargs.get("_nanobot_tool_call_id") or "").strip()

        if not thread_id:
            return json.dumps({"ok": False, "error": "present_fault_log_intake_card requires web chat thread context"}, ensure_ascii=False)
        if store is None:
            return json.dumps({"ok": False, "error": "pending_hitl_store not configured"}, ensure_ascii=False)
        if not tool_call_id:
            return json.dumps({"ok": False, "error": "missing tool_call_id"}, ensure_ascii=False)

        save_rel = str(kwargs.get("save_relative_dir") or "uploads/temp").strip().replace("\\", "/").strip("/") or "uploads/temp"
        parts = [p for p in save_rel.split("/") if p]
        if any(p in {".", ".."} for p in parts):
            return json.dumps({"ok": False, "error": "invalid save_relative_dir"}, ensure_ascii=False)

        request_id = uuid.uuid4().hex
        skill_run_id = f"agent:{thread_id}"

        payload: dict[str, Any] = {
            "requestId": request_id,
            "resumeAction": AGENT_UPLOAD_RESUME_ACTION,
            "title": "日志与现象接入",
            "purpose": FILE_PURPOSE,
            "skillName": AGENT_HITL_SKILL_NAME,
            "toolCallId": tool_call_id,
            "kind": "fault_log_intake",
        }
        envelope: dict[str, Any] = {
            "event": "hitl.text_request",
            "threadId": thread_id,
            "skillName": AGENT_HITL_SKILL_NAME,
            "skillRunId": skill_run_id,
            "payload": payload,
        }
        try:
            created = await store.create_pending_request(envelope)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        if not created:
            return json.dumps({"ok": False, "error": "duplicate requestId (unlikely)"}, ensure_ascii=False)

        docman = get_chat_docman()
        mc = MissionControlManager(thread_id=thread_id, docman=docman)
        handle = None
        try:
            handle = await mc.ask_for_text_input(
                purpose=FILE_PURPOSE,
                title="日志与现象接入",
                placeholder="…",
                rows=3,
                hitl_request_id=request_id,
                skill_name=AGENT_HITL_SKILL_NAME,
            )
            node = build_fault_log_intake_node(
                skill_name=AGENT_HITL_SKILL_NAME,
                hitl_request_id=request_id,
                save_relative_dir=save_rel,
            )
            await mc.replace_card(card_id=handle.card_id, title="日志与现象接入", node=node, doc_id=handle.doc_id)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

        return json.dumps(
            {
                "ok": True,
                "status": "pending_fault_intake",
                "requestId": request_id,
                "cardId": handle.card_id if handle else "",
                "saveRelativeDir": save_rel,
                "hint": "用户在单张卡片中上传日志并填写现象后点击「确认并启动诊断」；结果写入本工具调用的 tool 结果。",
            },
            ensure_ascii=False,
        )
