"""Agent tool: request structured file upload via HITL (MVP)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.web.mission_control import MissionControlManager

AGENT_HITL_SKILL_NAME = "nanobot_agent"
AGENT_UPLOAD_RESUME_ACTION = "agent_upload"

SAVE_LOCATION_ALIAS_MAP: dict[str, str] = {
    "zhgk_input": "skills/zhgk/ProjectData/Input",
    "temp_docs": "uploads/temp",
}


class RequestUserUploadTool(Tool):
    """Ask the user to upload files to a whitelisted workspace-relative location."""

    @property
    def name(self) -> str:
        return "request_user_upload"

    @property
    def description(self) -> str:
        return (
            "Request that the user upload one or more files. "
            "You MUST pass save_location_alias (not a raw path). "
            "After upload completes, the user may send another message (e.g. 继续) to resume. "
            f"Allowed aliases: {', '.join(sorted(SAVE_LOCATION_ALIAS_MAP))}."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short card title shown to the user"},
                "purpose": {
                    "type": "string",
                    "description": "Upload purpose label (forwarded to the upload API)",
                },
                "accept": {
                    "type": "string",
                    "description": "Optional HTML accept attribute, e.g. .pdf,.xlsx",
                },
                "multiple": {
                    "type": "boolean",
                    "description": "Allow multiple files",
                },
                "save_location_alias": {
                    "type": "string",
                    "enum": list(SAVE_LOCATION_ALIAS_MAP.keys()),
                    "description": "Whitelisted save location key",
                },
            },
            "required": ["title", "save_location_alias"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        from nanobot.agent.loop import get_current_thread_id, get_pending_hitl_store

        thread_id = (get_current_thread_id() or "").strip()
        store = get_pending_hitl_store()
        tool_call_id = str(kwargs.get("_nanobot_tool_call_id") or "").strip()

        title = str(kwargs.get("title") or "").strip() or "请上传文件"
        purpose = str(kwargs.get("purpose") or "").strip() or "file"
        accept = str(kwargs.get("accept") or "").strip() or None
        multiple = bool(kwargs.get("multiple"))
        alias = str(kwargs.get("save_location_alias") or "").strip()

        if not thread_id:
            return json.dumps({"ok": False, "error": "request_user_upload requires web chat thread context"}, ensure_ascii=False)
        if store is None:
            return json.dumps({"ok": False, "error": "pending_hitl_store not configured"}, ensure_ascii=False)
        if not tool_call_id:
            return json.dumps({"ok": False, "error": "missing tool_call_id"}, ensure_ascii=False)

        save_rel = SAVE_LOCATION_ALIAS_MAP.get(alias)
        if not save_rel:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"invalid save_location_alias; allowed: {list(SAVE_LOCATION_ALIAS_MAP)}",
                },
                ensure_ascii=False,
            )

        request_id = uuid.uuid4().hex
        skill_run_id = f"agent:{thread_id}"

        payload: dict[str, Any] = {
            "requestId": request_id,
            "resumeAction": AGENT_UPLOAD_RESUME_ACTION,
            "title": title,
            "purpose": purpose,
            "accept": accept,
            "multiple": multiple,
            "saveRelativeDir": save_rel,
            "skillName": AGENT_HITL_SKILL_NAME,
            "toolCallId": tool_call_id,
            "kind": "agent_upload",
        }

        envelope: dict[str, Any] = {
            "event": "hitl.file_request",
            "threadId": thread_id,
            "skillName": AGENT_HITL_SKILL_NAME,
            "skillRunId": skill_run_id,
            "payload": payload,
        }

        try:
            await store.create_pending_request(envelope)
        except Exception as e:
            logger.exception("request_user_upload pending failed | rid={}", request_id)
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

        from nanobot.agent.loop import get_chat_docman

        docman = get_chat_docman()
        mc = MissionControlManager(thread_id=thread_id, docman=docman)
        try:
            await mc.ask_for_file(
                purpose=purpose,
                title=title,
                accept=accept,
                multiple=multiple,
                mode="append",
                card_id=None,
                hitl_request_id=request_id,
                module_id=None,
                next_action=None,
                save_relative_dir=save_rel,
                skill_name=AGENT_HITL_SKILL_NAME,
                state_namespace=None,
                step_id=None,
                help_text=None,
            )
        except Exception as e:
            logger.exception("request_user_upload ask_for_file failed | rid={}", request_id)
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

        return json.dumps(
            {
                "ok": True,
                "status": "pending_user_upload",
                "requestId": request_id,
                "save_location_alias": alias,
                "saveRelativeDir": save_rel,
                "hint": "等待用户上传；上传完成后用户可发送「继续」以进行下一步推理。",
            },
            ensure_ascii=False,
        )
