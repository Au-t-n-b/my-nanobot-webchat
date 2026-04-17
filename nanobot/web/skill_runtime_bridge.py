"""Bridge standardized skill runtime events onto existing platform emitters."""

from __future__ import annotations

import json
from typing import Any

from nanobot.web.mission_control import MissionControlManager
from nanobot.web.skill_ui_patch import build_skill_ui_data_patch_payload
from nanobot.web.task_progress import normalize_task_progress_payload
from nanobot.web.skills import get_skill_dir

SUPPORTED_SKILL_RUNTIME_EVENTS = {
    "chat.guidance",
    "dashboard.bootstrap",
    "dashboard.patch",
    "hitl.file_request",
    "hitl.choice_request",
    "hitl.confirm_request",
    "artifact.publish",
    "task_progress.sync",
}


def _payload_from_envelope(envelope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    event = str(envelope.get("event") or "").strip()
    payload = envelope.get("payload")
    if not event:
        raise ValueError("skill runtime envelope missing event")
    if not isinstance(payload, dict):
        payload = {}
    if event not in SUPPORTED_SKILL_RUNTIME_EVENTS:
        raise ValueError(f"unsupported skill runtime event: {event}")
    return event, payload


def _try_load_skill_dashboard_bootstrap(skill_name: str) -> dict[str, Any] | None:
    """Best-effort build a SkillUiBootstrap payload for a local skill dashboard.

    Some Skill-First modules start via ``skill_runtime_start`` without the user
    manually mounting the dashboard first. In that case, emitting a bootstrap
    ensures the right-side panel can open immediately and subsequent patches
    have a mounted document to target.
    """
    name = str(skill_name or "").strip()
    if not name:
        return None
    try:
        skill_dir = get_skill_dir(name)
    except Exception:
        return None
    if not skill_dir.is_dir():
        return None

    module_doc_id = ""
    module_data_file = ""
    module_file = skill_dir / "module.json"
    if module_file.is_file():
        try:
            raw = json.loads(module_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                module_doc_id = str(raw.get("docId") or "").strip()
                module_data_file = str(raw.get("dataFile") or "").strip()
        except Exception:
            module_doc_id = ""
            module_data_file = ""

    dashboard_path = skill_dir / "data" / "dashboard.json"
    if not dashboard_path.is_file():
        return None
    try:
        document = json.loads(dashboard_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(document, dict):
        return None

    data_file = module_data_file or f"skills/{name}/data/dashboard.json"
    doc_id = (
        module_doc_id
        or str((document.get("meta") or {}).get("docId") or "").strip()
        or "dashboard:runtime"
    )
    synthetic_path = f"skill-ui://SduiView?dataFile={data_file}"
    return {"syntheticPath": synthetic_path, "docId": doc_id, "document": document}


async def _emit_guidance(
    *,
    mc: MissionControlManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    context = str(payload.get("context") or "").strip() or "请继续下一步。"
    raw_actions = payload.get("actions")
    actions = [dict(item) for item in raw_actions if isinstance(item, dict)] if isinstance(raw_actions, list) else []
    handle = await mc.emit_guidance(
        context,
        actions,
        card_id=str(payload.get("cardId") or "").strip() or None,
    )
    return {
        "ok": True,
        "event": "chat.guidance",
        "summary": context,
        "cardId": handle.card_id,
        "docId": handle.doc_id,
    }


async def _emit_file_request(
    *,
    mc: MissionControlManager,
    payload: dict[str, Any],
    envelope: dict[str, Any] | None = None,
    pending_hitl_store: Any = None,
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip() or "请上传文件"
    hitl_rid = str(payload.get("requestId") or "").strip() or None
    final_skill_name = str(payload.get("skillName") or (envelope or {}).get("skillName") or "").strip() or None
    # Persist pending HITL (idempotent) when store is configured.
    if pending_hitl_store is not None and envelope is not None:
        await pending_hitl_store.create_pending_request(envelope)
    handle = await mc.ask_for_file(
        purpose=str(payload.get("purpose") or "").strip() or "file",
        title=title,
        accept=str(payload.get("accept") or "").strip() or None,
        multiple=bool(payload.get("multiple")),
        mode="replace" if str(payload.get("mode") or "").strip() == "replace" else "append",
        card_id=str(payload.get("cardId") or "").strip() or None,
        hitl_request_id=hitl_rid,
        module_id=str(payload.get("moduleId") or "").strip() or None,
        next_action=str(payload.get("resumeAction") or "").strip() or None,
        save_relative_dir=str(payload.get("saveRelativeDir") or "").strip() or None,
        skill_name=final_skill_name,
        state_namespace=str(payload.get("stateNamespace") or "").strip() or None,
        step_id=str(payload.get("stepId") or "").strip() or None,
    )
    return {
        "ok": True,
        "event": "hitl.file_request",
        "summary": title,
        "cardId": handle.card_id,
        "docId": handle.doc_id,
    }


async def _emit_choice_request(
    *,
    mc: MissionControlManager,
    payload: dict[str, Any],
    envelope: dict[str, Any] | None = None,
    pending_hitl_store: Any = None,
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip() or "请选择"
    hitl_rid = str(payload.get("requestId") or "").strip() or None
    final_skill_name = str(payload.get("skillName") or (envelope or {}).get("skillName") or "").strip() or None
    raw_options = payload.get("options")
    options = [dict(item) for item in raw_options if isinstance(item, dict)] if isinstance(raw_options, list) else []
    if pending_hitl_store is not None and envelope is not None:
        await pending_hitl_store.create_pending_request(envelope)
    handle = await mc.emit_choices(
        title,
        options,
        card_id=str(payload.get("cardId") or "").strip() or None,
        hitl_request_id=hitl_rid,
        module_id=str(payload.get("moduleId") or "").strip() or None,
        next_action=str(payload.get("resumeAction") or "").strip() or None,
        skill_name=final_skill_name,
        state_namespace=str(payload.get("stateNamespace") or "").strip() or None,
        step_id=str(payload.get("stepId") or "").strip() or None,
    )
    return {
        "ok": True,
        "event": "hitl.choice_request",
        "summary": title,
        "cardId": handle.card_id,
        "docId": handle.doc_id,
    }


async def _emit_confirm_request(
    *,
    mc: MissionControlManager,
    payload: dict[str, Any],
    envelope: dict[str, Any] | None = None,
    pending_hitl_store: Any = None,
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip() or "请确认"
    confirm_label = str(payload.get("confirmLabel") or "").strip() or "确认"
    cancel_label = str(payload.get("cancelLabel") or "").strip() or "取消"
    hitl_rid = str(payload.get("requestId") or "").strip() or None
    final_skill_name = str(payload.get("skillName") or (envelope or {}).get("skillName") or "").strip() or None
    if pending_hitl_store is not None and envelope is not None:
        await pending_hitl_store.create_pending_request(envelope)
    handle = await mc.emit_confirm(
        title,
        confirm_label=confirm_label,
        cancel_label=cancel_label,
        card_id=str(payload.get("cardId") or "").strip() or None,
        hitl_request_id=hitl_rid,
        module_id=str(payload.get("moduleId") or "").strip() or None,
        next_action=str(payload.get("resumeAction") or "").strip() or None,
        skill_name=final_skill_name,
        state_namespace=str(payload.get("stateNamespace") or "").strip() or None,
        step_id=str(payload.get("stepId") or "").strip() or None,
    )
    return {
        "ok": True,
        "event": "hitl.confirm_request",
        "summary": title,
        "cardId": handle.card_id,
        "docId": handle.doc_id,
    }


async def _emit_dashboard_patch(payload: dict[str, Any]) -> dict[str, Any]:
    synthetic_path = str(payload.get("syntheticPath") or "").strip()
    doc_id = str(payload.get("docId") or "").strip() or "dashboard:runtime"
    raw_ops = payload.get("ops")
    ops = [dict(item) for item in raw_ops if isinstance(item, dict)] if isinstance(raw_ops, list) else []
    patch_payload = await build_skill_ui_data_patch_payload(
        synthetic_path=synthetic_path,
        doc_id=doc_id,
        ops=ops,
        is_partial=bool(payload.get("isPartial")),
    )
    from nanobot.agent.loop import emit_skill_ui_data_patch_event

    await emit_skill_ui_data_patch_event(patch_payload)
    return {
        "ok": True,
        "event": "dashboard.patch",
        "summary": f"已更新大盘: {doc_id}",
        "docId": doc_id,
        "syntheticPath": synthetic_path,
    }


async def _emit_dashboard_bootstrap(payload: dict[str, Any]) -> dict[str, Any]:
    synthetic_path = str(payload.get("syntheticPath") or "").strip()
    doc_id = str(payload.get("docId") or "").strip() or "dashboard:runtime"
    document = payload.get("document")
    from nanobot.agent.loop import emit_skill_ui_bootstrap_event

    await emit_skill_ui_bootstrap_event(
        {
            "syntheticPath": synthetic_path,
            "docId": doc_id,
            "document": document,
        }
    )
    return {
        "ok": True,
        "event": "dashboard.bootstrap",
        "summary": f"已初始化大盘: {doc_id}",
        "docId": doc_id,
        "syntheticPath": synthetic_path,
    }


async def _emit_artifact_publish(
    *,
    mc: MissionControlManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    synthetic_path = str(payload.get("syntheticPath") or "").strip()
    doc_id = str(payload.get("docId") or "").strip() or "dashboard:runtime"
    artifacts_node_id = str(payload.get("artifactsNodeId") or "").strip() or "artifacts"
    raw_items = payload.get("items")
    items = [dict(item) for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    for index, item in enumerate(items, start=1):
        await mc.add_artifact(
            doc_id,
            synthetic_path=synthetic_path,
            artifact_id=str(item.get("artifactId") or f"artifact-{index}").strip() or f"artifact-{index}",
            label=str(item.get("label") or f"产物 {index}").strip() or f"产物 {index}",
            path=str(item.get("path") or "").strip(),
            kind=str(item.get("kind") or "other").strip() or "other",
            status=str(item.get("status") or "ready").strip() or "ready",
            artifacts_node_id=artifacts_node_id,
        )
    summary = f"已发布 {len(items)} 个产物" if items else "未发布产物"
    return {
        "ok": True,
        "event": "artifact.publish",
        "summary": summary,
        "count": len(items),
        "docId": doc_id,
    }


async def _emit_task_progress_sync(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_task_progress_payload(dict(payload))
    from nanobot.agent.loop import emit_task_status_event

    await emit_task_status_event(normalized)
    return {
        "ok": True,
        "event": "task_progress.sync",
        "summary": "已同步项目进展",
        "modules": normalized.get("modules") if isinstance(normalized, dict) else [],
    }


async def emit_skill_runtime_event(
    *,
    envelope: dict[str, Any],
    thread_id: str,
    docman: Any = None,
    pending_hitl_store: Any = None,
) -> dict[str, Any]:
    event, payload = _payload_from_envelope(envelope)
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    if event == "chat.guidance":
        return await _emit_guidance(mc=mc, payload=payload)
    if event == "hitl.file_request":
        # Ensure envelope contains thread/skill/run identifiers for persistence.
        enriched = dict(envelope)
        # Always use the platform chat session id: driver stdout may carry
        # ``thread-unknown`` or a stale value; setdefault would keep the wrong id and
        # ``PendingHitlStore.consume_result`` would raise thread_id mismatch on upload.
        enriched["threadId"] = thread_id
        return await _emit_file_request(
            mc=mc,
            payload=payload,
            envelope=enriched,
            pending_hitl_store=pending_hitl_store,
        )
    if event == "hitl.choice_request":
        enriched = dict(envelope)
        enriched["threadId"] = thread_id
        return await _emit_choice_request(
            mc=mc,
            payload=payload,
            envelope=enriched,
            pending_hitl_store=pending_hitl_store,
        )
    if event == "hitl.confirm_request":
        enriched = dict(envelope)
        enriched["threadId"] = thread_id
        return await _emit_confirm_request(
            mc=mc,
            payload=payload,
            envelope=enriched,
            pending_hitl_store=pending_hitl_store,
        )
    if event == "dashboard.patch":
        return await _emit_dashboard_patch(payload)
    if event == "dashboard.bootstrap":
        return await _emit_dashboard_bootstrap(payload)
    if event == "artifact.publish":
        return await _emit_artifact_publish(mc=mc, payload=payload)
    if event == "task_progress.sync":
        return await _emit_task_progress_sync(payload)
    raise ValueError(f"unsupported skill runtime event: {event}")


async def dispatch_skill_runtime_intent(
    intent: dict[str, Any] | None,
    *,
    thread_id: str,
    docman: Any = None,
    pending_hitl_store: Any = None,
    resume_runner: Any = None,
) -> tuple[bool, str]:
    if not intent:
        return False, ""

    verb = str(intent.get("verb") or "").strip()
    payload = intent.get("payload")
    if verb == "skill_runtime_start":
        if not isinstance(payload, dict):
            return True, "skill_runtime_start payload 非法"
        skill_name = str(payload.get("skillName") or "").strip()
        request_id = str(payload.get("requestId") or "").strip()
        action = str(payload.get("action") or "").strip()
        tid = str(payload.get("threadId") or "").strip() or thread_id
        if not skill_name or not request_id or not action:
            return True, "skill_runtime_start 缺少必要字段（skillName/requestId/action）"
        if tid != thread_id:
            return True, "skill_runtime_start threadId 不匹配"
        if resume_runner is None:
            return True, "skill_runtime_start：resume_runner 未配置"

        bootstrap = _try_load_skill_dashboard_bootstrap(skill_name)
        if bootstrap is not None:
            try:
                from nanobot.agent.loop import emit_skill_ui_bootstrap_event

                await emit_skill_ui_bootstrap_event(bootstrap)
            except Exception:
                # Best-effort: do not block skill execution on UI bootstrap.
                pass

        out = await resume_runner(
            thread_id=thread_id,
            skill_name=skill_name,
            request_id=request_id,
            action=action,
            status="ok",
            result={},
        )
        if isinstance(out, dict) and out.get("ok") is True:
            return True, "skill_runtime_start resumed"
        return True, "skill_runtime_start 执行失败"
    if verb == "skill_runtime_event":
        if not isinstance(payload, dict):
            return True, "skill_runtime_event payload 非法"
        result = await emit_skill_runtime_event(
            envelope=payload,
            thread_id=thread_id,
            docman=docman,
            pending_hitl_store=pending_hitl_store,
        )
        if result.get("ok") is True:
            return True, str(result.get("summary") or "").strip()
        return True, str(result.get("error") or "操作失败").strip()

    # Skill-First: direct resume for interactive UI events (non-HITL).
    # This verb bypasses PendingHitlStore entirely.
    if verb == "skill_runtime_resume":
        if not isinstance(payload, dict):
            return True, "skill_runtime_resume payload 非法"
        if str(payload.get("type") or "").strip() != "skill_runtime_resume":
            return True, "skill_runtime_resume.type 非法"

        tid = str(payload.get("threadId") or "").strip() or thread_id
        if tid != thread_id:
            return True, "skill_runtime_resume threadId 不匹配"

        skill_name = str(payload.get("skillName") or "").strip()
        request_id = str(payload.get("requestId") or "").strip()
        action = str(payload.get("action") or "").strip()
        status = str(payload.get("status") or "").strip()
        result_obj = payload.get("result")

        missing = [k for k in ["skillName", "requestId", "action", "status"] if not str(payload.get(k) or "").strip()]
        if missing:
            return True, f"skill_runtime_resume 缺少必要字段：{','.join(missing)}"
        if status not in {"ok", "cancel", "timeout", "error"}:
            return True, "skill_runtime_resume.status 非法"
        if resume_runner is None:
            return True, "skill_runtime_resume：resume_runner 未配置"

        out = await resume_runner(
            thread_id=thread_id,
            skill_name=skill_name,
            request_id=request_id,
            action=action,
            status=status,
            result=result_obj if result_obj is not None else {},
        )
        if isinstance(out, dict) and out.get("ok") is True:
            # Silent success: UI updates are delivered via SSE events (dashboard.patch/artifact.publish).
            # Avoid polluting the chat transcript with a completion line.
            return True, ""
        return True, "skill_runtime_resume 执行失败"

    # Hard Rule: runtime results must be ingested via /api/chat fast-path intent.
    if verb == "skill_runtime_result":
        if not isinstance(payload, dict):
            return True, "skill_runtime_result payload 非法"
        # Outermost schema validation (Hard Rule): reject bad envelopes before touching store.
        required = {
            "type": "skill_runtime_result",
        }
        if str(payload.get("type") or "").strip() != required["type"]:
            return True, "skill_runtime_result.type 非法"
        # threadId can be omitted by UI surfaces (SDUI buttons / EmbeddedWeb).
        # Hard Rule still applies when provided: must match current thread_id.
        p_thread = str(payload.get("threadId") or "").strip()
        if not p_thread:
            payload["threadId"] = thread_id
            p_thread = str(thread_id)
        p_skill = str(payload.get("skillName") or "").strip()
        p_req = str(payload.get("requestId") or "").strip()
        p_status = str(payload.get("status") or "").strip()
        if not p_skill or not p_req or not p_status:
            missing = [k for k in ["skillName", "requestId", "status"] if not str(payload.get(k) or "").strip()]
            return True, f"skill_runtime_result 缺少必要字段：{','.join(missing)}"
        if p_thread != str(thread_id):
            return True, "skill_runtime_result threadId 不匹配"
        if p_status not in {"ok", "cancel", "timeout", "error"}:
            return True, "skill_runtime_result.status 非法"
        if pending_hitl_store is None:
            return True, "skill_runtime_result：pending_hitl_store 未配置"
        # Opportunistic zombie prevention: advance timeouts before consuming results.
        try:
            await pending_hitl_store.timeout_expired_requests()
        except Exception:
            # Timeout scan is best-effort; do not block result ingestion.
            pass
        out = await pending_hitl_store.consume_result(payload)
        if out.get("ok") is True and out.get("duplicate") is True:
            return True, "skill_runtime_result duplicate (idempotent)"
        if out.get("ok") is True:
            if resume_runner is None:
                return True, "skill_runtime_result consumed"
            # Use resolved action/result from store replay to enforce fallback routing hard rules.
            rid = str(payload.get("requestId") or "").strip()
            resolved_action = str(payload.get("action") or "").strip()
            resolved_status = str(payload.get("status") or "").strip()
            resolved_result = payload.get("result")
            try:
                replay = await pending_hitl_store.get_result_for_request(rid)
            except Exception:
                replay = None
            if isinstance(replay, dict):
                resolved_action = str(replay.get("action") or resolved_action)
                raw = replay.get("result_json")
                if isinstance(raw, str) and raw.strip():
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            resolved_status = str(parsed.get("status") or resolved_status)
                            if "result" in parsed:
                                resolved_result = parsed.get("result")
                    except json.JSONDecodeError:
                        pass
            await resume_runner(
                thread_id=str(payload.get("threadId") or "").strip(),
                skill_name=str(payload.get("skillName") or "").strip(),
                request_id=rid,
                action=resolved_action,
                status=resolved_status,
                result=resolved_result,
            )
            return True, "skill_runtime_result resumed"
        return True, "skill_runtime_result 处理失败"

    return False, ""
