"""Mission Control Manager (Milestone ChatCard + Upload).

MissionControlManager is a lightweight "diplomat" that can request structured
user inputs (e.g. file upload) through the SkillUiChatCard SSE channel, while
keeping DocManager as the truth store.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.web.doc_manager import DocManager


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class ChatCardHandle:
    card_id: str
    doc_id: str


class MissionControlManager:
    """Base Mission Control manager.

    This class is intentionally thin and can be instantiated per /api/chat run.
    It emits SkillUiChatCard payloads and ensures a doc exists in DocManager.
    """

    def __init__(
        self,
        *,
        thread_id: str,
        docman: DocManager | None,
        # Optional hook for tests/alternate emitters; default uses agent.loop emitter.
        emit_chat_card: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self.thread_id = str(thread_id or "").strip()
        self.docman = docman
        # NOTE: avoid importing nanobot.agent.loop at module import time (prevents circular import).
        self._emit: Callable[[dict[str, Any]], Awaitable[None]] | None = emit_chat_card

    async def _emit_chat_card(self, payload: dict[str, Any]) -> None:
        cb = self._emit
        if cb is None:
            try:
                # Lazy import breaks circular dependency: agent.loop imports tools which import mission_control.
                from nanobot.agent.loop import emit_skill_ui_chat_card_event

                cb = emit_skill_ui_chat_card_event
            except Exception as e:
                logger.debug("MissionControl emit unavailable | {}", e)
                return
        await cb(payload)

    def _chat_doc_id(self) -> str:
        return f"chat:{self.thread_id or 'unknown'}"

    async def _ensure_chat_doc(self) -> str:
        did = self._chat_doc_id()
        if self.docman is None:
            return did
        # Minimal doc shell: Stack root. Truth starts at revision=0.
        doc = {
            "schemaVersion": 1,
            "type": "SduiDocument",
            "meta": {"docId": did, "provenance": "mission-control"},
            "root": {"type": "Stack", "gap": "md", "children": []},
        }
        try:
            await self.docman.ensure_doc(doc_id=did, initial_doc=doc, revision=0, persist_path_hint=None)
        except Exception as e:
            # It's okay if already exists; ensure_doc is idempotent-ish for same docId.
            logger.debug("MissionControl ensure_doc skipped/failed | docId={} | {}", did, e)
        return did

    async def ask_for_file(
        self,
        *,
        purpose: str,
        title: str,
        accept: str | None = None,
        multiple: bool = False,
        mode: str = "append",
        card_id: str | None = None,
        hitl_request_id: str | None = None,
        module_id: str | None = None,
        next_action: str | None = None,
        save_relative_dir: str | None = None,
        skill_name: str | None = None,
        state_namespace: str | None = None,
        step_id: str | None = None,
    ) -> ChatCardHandle:
        """Emit a chat card that asks user to upload a file.

        Returns handle containing stable card_id and doc_id.
        """
        p = (purpose or "").strip() or "file"
        t = (title or "").strip() or "请上传文件"
        did = await self._ensure_chat_doc()
        cid = (card_id or "").strip() or f"upload:{p}:{uuid.uuid4().hex}"
        save_dir = (save_relative_dir or "").strip().replace("\\", "/").strip("/")
        fp_node: dict[str, Any] = {
            "type": "FilePicker",
            "purpose": p,
            "accept": (accept or "").strip() or None,
            "multiple": bool(multiple),
            "label": "上传文件",
            "helpText": (
                f"将文件拖到下方区域或点击选择；支持多文件与补充追加上传；保存目录（workspace 相对）：{save_dir}/<文件名>"
                if save_dir
                else "将文件拖到下方区域或点击选择；支持多文件与补充追加上传；上传成功后会同步会话、大盘并触发下一步。"
            ),
        }
        mid = (module_id or "").strip()
        na = (next_action or "").strip()
        if mid:
            fp_node["moduleId"] = mid
        if na:
            fp_node["nextAction"] = na
        if save_dir:
            fp_node["saveRelativeDir"] = save_dir
        skill = (skill_name or "").strip()
        namespace = (state_namespace or "").strip()
        sid = (step_id or "").strip()
        if skill:
            fp_node["skillName"] = skill
        if namespace:
            fp_node["stateNamespace"] = namespace
        if sid:
            fp_node["stepId"] = sid
        hr = (hitl_request_id or "").strip()
        if hr:
            # Must match PendingHitlStore primary key (HITL envelope payload.requestId).
            fp_node["hitlRequestId"] = hr
        payload: dict[str, Any] = {
            "threadId": self.thread_id,
            "cardId": cid,
            "mode": "replace" if str(mode) == "replace" else "append",
            "docId": did,
            "title": t,
            "node": fp_node,
        }
        await self._emit_chat_card(payload)
        return ChatCardHandle(card_id=cid, doc_id=did)

    async def replace_card(
        self,
        *,
        card_id: str,
        title: str,
        node: dict[str, Any],
        doc_id: str | None = None,
    ) -> ChatCardHandle:
        """Replace an existing chat card (mode=replace) with a new SDUI node tree."""
        cid = str(card_id or "").strip()
        if not cid:
            raise ValueError("card_id is required")
        did = (str(doc_id or "").strip() or await self._ensure_chat_doc())
        payload: dict[str, Any] = {
            "threadId": self.thread_id,
            "cardId": cid,
            "mode": "replace",
            "docId": did,
            "title": str(title or "").strip() or None,
            "node": node,
        }
        await self._emit_chat_card(payload)
        return ChatCardHandle(card_id=cid, doc_id=did)

    async def add_artifact(
        self,
        doc_id: str,
        *,
        synthetic_path: str,
        artifact_id: str,
        label: str,
        path: str,
        kind: str = "other",
        status: str = "ready",
        artifacts_node_id: str = "artifacts",
    ) -> None:
        """Append an artifact pill via v3 SkillUiDataPatch (syntheticPath + SduiPatch)."""
        from nanobot.agent.loop import emit_skill_ui_data_patch_event  # lazy import
        from nanobot.web.skill_ui_patch import build_append_op, build_skill_ui_data_patch_payload

        try:
            ops = [
                build_append_op(
                    node_id=artifacts_node_id,
                    field="artifacts",
                    value={
                        "id": artifact_id,
                        "label": label,
                        "path": path,
                        "kind": kind,
                        "status": status,
                    },
                )
            ]
            payload = await build_skill_ui_data_patch_payload(
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                ops=ops,
            )
            await emit_skill_ui_data_patch_event(payload)
        except Exception as exc:
            logger.error("add_artifact emit failed | {}", exc)

    async def emit_guidance(
        self,
        context: str,
        actions: list[dict[str, Any]],
        *,
        card_id: str | None = None,
    ) -> ChatCardHandle:
        """Send a GuidanceCard to the chat stream.

        Args:
            context: Human-readable progress description, e.g. "Step 2 complete, recommend continuing Step 3".
            actions: Quick action list, format [{"label": "继续", "verb": "proceed"}, ...].
            card_id: Optional; used for later replace. Auto-generated if not provided.
        """
        cid = card_id or str(uuid.uuid4())
        did = await self._ensure_chat_doc()
        node: dict[str, Any] = {
            "type": "GuidanceCard",
            "id": f"guidance-{cid}",
            "context": context,
            "actions": actions,
        }
        payload: dict[str, Any] = {
            "threadId": self.thread_id,
            "cardId": cid,
            "docId": did,
            "mode": "replace" if card_id else "append",
            "node": node,
            "ts": _now_ms(),
        }
        await self._emit_chat_card(payload)
        return ChatCardHandle(card_id=cid, doc_id=did)

    async def emit_choices(
        self,
        title: str,
        options: list[dict[str, str]],
        *,
        card_id: str | None = None,
        hitl_request_id: str | None = None,
        module_id: str | None = None,
        next_action: str | None = None,
        skill_name: str | None = None,
        state_namespace: str | None = None,
        step_id: str | None = None,
    ) -> ChatCardHandle:
        """Send a ChoiceCard to the chat stream.

        Args:
            title: Question title, e.g. "请确认本次勘察的电压等级：".
            options: Options list, format [{"id": "10kv", "label": "10kV 低压配网"}, ...].
            card_id: Optional; auto-generated if not provided.
        """
        cid = card_id or str(uuid.uuid4())
        did = await self._ensure_chat_doc()
        node: dict[str, Any] = {
            "type": "ChoiceCard",
            "id": f"choice-{cid}",
            "title": title,
            "options": options,
        }
        mid = (module_id or "").strip()
        na = (next_action or "").strip()
        if mid:
            node["moduleId"] = mid
        if na:
            node["nextAction"] = na
        skill = (skill_name or "").strip()
        namespace = (state_namespace or "").strip()
        sid = (step_id or "").strip()
        if skill:
            node["skillName"] = skill
        if namespace:
            node["stateNamespace"] = namespace
        if sid:
            node["stepId"] = sid
        hr = (hitl_request_id or "").strip()
        if hr:
            node["hitlRequestId"] = hr
        payload: dict[str, Any] = {
            "threadId": self.thread_id,
            "cardId": cid,
            "docId": did,
            "mode": "append",
            "node": node,
            "ts": _now_ms(),
        }
        await self._emit_chat_card(payload)
        return ChatCardHandle(card_id=cid, doc_id=did)

    async def emit_confirm(
        self,
        title: str,
        *,
        confirm_label: str,
        cancel_label: str,
        card_id: str | None = None,
        hitl_request_id: str | None = None,
        module_id: str | None = None,
        next_action: str | None = None,
        skill_name: str | None = None,
        state_namespace: str | None = None,
        step_id: str | None = None,
    ) -> ChatCardHandle:
        """Send a ConfirmCard to the chat stream."""
        cid = card_id or str(uuid.uuid4())
        did = await self._ensure_chat_doc()
        node: dict[str, Any] = {
            "type": "ConfirmCard",
            "id": f"confirm-{cid}",
            "title": str(title or "").strip() or "请确认",
            "confirmLabel": str(confirm_label or "").strip() or "确认",
            "cancelLabel": str(cancel_label or "").strip() or "取消",
        }
        mid = (module_id or "").strip()
        na = (next_action or "").strip()
        if mid:
            node["moduleId"] = mid
        if na:
            node["nextAction"] = na
        skill = (skill_name or "").strip()
        namespace = (state_namespace or "").strip()
        sid = (step_id or "").strip()
        if skill:
            node["skillName"] = skill
        if namespace:
            node["stateNamespace"] = namespace
        if sid:
            node["stepId"] = sid
        hr = (hitl_request_id or "").strip()
        if hr:
            node["hitlRequestId"] = hr
        payload: dict[str, Any] = {
            "threadId": self.thread_id,
            "cardId": cid,
            "docId": did,
            "mode": "append",
            "node": node,
            "ts": _now_ms(),
        }
        await self._emit_chat_card(payload)
        return ChatCardHandle(card_id=cid, doc_id=did)
