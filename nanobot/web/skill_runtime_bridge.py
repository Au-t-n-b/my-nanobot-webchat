"""Bridge standardized skill runtime events onto existing platform emitters."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal

from loguru import logger

import os
from pathlib import Path

from nanobot.web.mission_control import MissionControlManager
from nanobot.web.skill_ui_patch import build_skill_ui_data_patch_payload
from nanobot.web.task_progress import normalize_task_progress_payload
from nanobot.web.skills import get_skill_dir

# Must match ``resumeAction`` / stored action for agent ``request_user_upload`` HITL.
AGENT_UPLOAD_RESUME_ACTION = "agent_upload"

# Template / NL ``skill_runtime_start`` often uses a stable ``requestId`` (e.g. ``req-start-zhgk``).
# PendingHitlStore uses ``request_id`` as PRIMARY KEY with INSERT OR IGNORE; once consumed, a second
# run must use a new id or ``create_pending_request`` is skipped and ``skill_runtime_result`` only
# ever sees duplicate consumes (no resume_runner).
_START_RUN_NONCE_RE = re.compile(r":[0-9a-f]{12}$", re.IGNORECASE)


def _ensure_unique_skill_runtime_start_request_id(payload: dict[str, Any]) -> str:
    """If ``requestId`` lacks a trailing 12-hex run nonce, append ``:<nonce>`` (mutates payload)."""
    rid = str(payload.get("requestId") or "").strip()
    if not rid:
        return ""
    if _START_RUN_NONCE_RE.search(rid):
        return rid
    new_rid = f"{rid}:{uuid.uuid4().hex[:12]}"
    payload["requestId"] = new_rid
    return new_rid


SUPPORTED_SKILL_RUNTIME_EVENTS = {
    "chat.guidance",
    "dashboard.bootstrap",
    "dashboard.patch",
    "hitl.file_request",
    "hitl.choice_request",
    "hitl.confirm_request",
    "artifact.publish",
    "task_progress.sync",
    "skill.agent_task_execute",
    "skill.epilogue",
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
    desc = str(payload.get("description") or "").strip() or None
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
        help_text=desc,
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


def _hybrid_task_progress_payload(
    *,
    skill_name: str,
    task_id: str,
    step_label: str,
    outcome_phase: Literal["running", "success", "failed", "skipped"],
) -> dict[str, Any]:
    """Single-module snapshot for TaskStatusUpdate (merged client-side by module id).

    Hybrid lanes use module id ``hybrid:{skill}``. Terminal phases must not mislabel
    failures/skips as ``completed`` — frontend filters ``hybrid:`` from global progress.
    """
    now_ms = int(datetime.now().timestamp() * 1000)
    mod_id = f"hybrid:{skill_name}"
    if outcome_phase == "running":
        overall = {"doneCount": 0, "totalCount": 1}
        mod_status = "running"
        step_done = False
    elif outcome_phase == "success":
        overall = {"doneCount": 1, "totalCount": 1}
        mod_status = "completed"
        step_done = True
    elif outcome_phase == "failed":
        overall = {"doneCount": 0, "totalCount": 1}
        mod_status = "failed"
        step_done = True
    else:  # skipped
        overall = {"doneCount": 0, "totalCount": 1}
        mod_status = "skipped"
        step_done = True
    return {
        "updatedAt": now_ms,
        "overall": overall,
        "modules": [
            {
                "id": mod_id,
                "name": f"受控Agent·{skill_name}",
                "status": mod_status,
                "steps": [
                    {
                        "id": (task_id or mod_id)[:80],
                        "name": (step_label or "子任务")[:120],
                        "done": step_done,
                    }
                ],
            }
        ],
    }


async def _emit_skill_agent_task_execute(
    *,
    envelope: dict[str, Any],
    payload: dict[str, Any],
    thread_id: str,
    agent_loop: Any,
) -> dict[str, Any]:
    """Execute a bounded Agent subtask inside the skill resume chain (await-friendly)."""
    from nanobot.web.hybrid_agent_subtask import run_hybrid_agent_subtask
    from nanobot.web.skill_ui_patch import _merge_op_for_node

    envelope_skill = str(envelope.get("skillName") or "").strip()
    skill_name = envelope_skill or str(payload.get("skillName") or "").strip() or "skill"
    task_id = str(payload.get("taskId") or "").strip() or f"hybrid-{uuid.uuid4().hex[:12]}"
    goal = str(payload.get("goal") or "").strip()
    if not goal:
        return {"ok": False, "event": "skill.agent_task_execute", "error": "missing_goal"}

    result_delivery = str(payload.get("resultDelivery") or "dashboard").strip().lower()
    use_sse = result_delivery == "sse"

    if use_sse:
        # Preview insight / ephemeral JSON: never delegate read_file (unbounded risk).
        allowed_tools = ["read_file_head", "read_file_tail", "read_hex_dump", "list_dir"]
    else:
        raw_allowed = payload.get("allowedTools")
        if isinstance(raw_allowed, list) and raw_allowed:
            allowed_tools = [str(x).strip() for x in raw_allowed if str(x).strip()]
        else:
            allowed_tools = ["read_file", "list_dir"]
        if not allowed_tools:
            allowed_tools = ["read_file", "list_dir"]

    try:
        max_iterations = int(payload.get("maxIterations") or 8)
    except (TypeError, ValueError):
        max_iterations = 8
    max_iterations = max(1, min(max_iterations, 32))

    step_hint = str(payload.get("stepId") or "hybrid.subtask").strip() or "hybrid.subtask"

    synthetic_path = str(payload.get("syntheticPath") or "").strip()
    doc_id = str(payload.get("docId") or "").strip() or "dashboard:runtime"
    summary_node_id = str(payload.get("summaryNodeId") or "summary-text").strip() or "summary-text"

    if agent_loop is None:
        await _emit_task_progress_sync(
            _hybrid_task_progress_payload(
                skill_name=skill_name,
                task_id=task_id,
                step_label="已跳过(无 Agent 会话绑定)",
                outcome_phase="skipped",
            )
        )
        logger.info(
            "skill.agent_task_execute skipped | thread_id={} task_id={} reason=no_agent_loop",
            thread_id,
            task_id,
        )
        return {"ok": True, "event": "skill.agent_task_execute", "taskId": task_id, "skipped": True}

    await _emit_task_progress_sync(
        _hybrid_task_progress_payload(
            skill_name=skill_name,
            task_id=task_id,
            step_label=step_hint,
            outcome_phase="running",
        )
    )

    hybrid = await run_hybrid_agent_subtask(
        agent_loop=agent_loop,
        goal=goal,
        allowed_tools=allowed_tools,
        max_iterations=max_iterations,
        output_mode="file_insight_json" if use_sse else "summary_zh",
    )
    ok = bool(hybrid.get("ok"))
    final_label = "子任务完成" if ok else f"失败: {str(hybrid.get('error') or '')}"[:120]
    await _emit_task_progress_sync(
        _hybrid_task_progress_payload(
            skill_name=skill_name,
            task_id=task_id,
            step_label=final_label,
            outcome_phase="success" if ok else "failed",
        )
    )

    text = str(hybrid.get("text") or "").strip()
    if not text:
        text = str(hybrid.get("error") or ("子任务失败" if not ok else "")).strip()

    if use_sse:
        from nanobot.agent.loop import emit_skill_agent_task_result_event

        report = hybrid.get("report")
        err = str(hybrid.get("error") or "").strip() or None
        sse_ok = bool(ok) and isinstance(report, dict)
        if not sse_ok and not err:
            err = "missing_or_invalid_report"
        try:
            await emit_skill_agent_task_result_event(
                {
                    "threadId": thread_id,
                    "taskId": task_id,
                    "ok": sse_ok,
                    "report": report if isinstance(report, dict) else None,
                    "error": err,
                }
            )
        except Exception as e:
            logger.warning("skill.agent_task_execute sse result emit failed | thread_id={} | {}", thread_id, e)
        summary = ""
        if isinstance(report, dict):
            summary = str(report.get("summary") or "")[:200]
        if not summary:
            summary = (text or final_label)[:200]
        return {
            "ok": True,
            "event": "skill.agent_task_execute",
            "taskId": task_id,
            "subtaskOk": sse_ok,
            "summary": summary,
        }

    if synthetic_path and text:
        try:
            # TODO(hybrid): merge op type is coupled to dashboard JSON; default Text matches gongkan summary-text.
            # Optional payload ``summaryNodeType`` must match the live node's ``type`` or the client drops the merge.
            summary_node_type = str(payload.get("summaryNodeType") or "Text").strip() or "Text"
            merge_op = _merge_op_for_node(
                summary_node_id,
                summary_node_type,
                {"content": text[:8000]},
            )
            await _emit_dashboard_patch(
                {
                    "syntheticPath": synthetic_path,
                    "docId": doc_id,
                    "ops": [merge_op],
                }
            )
        except Exception as e:
            logger.warning("skill.agent_task_execute patch failed | thread_id={} | {}", thread_id, e)

    return {
        "ok": True,
        "event": "skill.agent_task_execute",
        "taskId": task_id,
        "subtaskOk": ok,
        "summary": (text or final_label)[:200],
    }


def _skill_epilogue_user_prompt(stats: dict[str, Any]) -> str:
    parts = [
        "工勘流程已闭环，请根据以下摘要写一句结案陈词（仅一句）。",
        f"场景：{str(stats.get('scenario') or '未标注')}",
        f"风险/遗留条目数：{int(stats.get('risk_rows') or 0)}",
        f"产物条目数：{int(stats.get('artifact_count') or 0)}",
        f"勘测项：已填 {int(stats.get('survey_filled') or 0)} / 共 {int(stats.get('survey_total') or 0)}",
    ]
    ct = str(stats.get("cooling_tag") or "").strip()
    if ct:
        parts.append(f"冷却标签：{ct}")
    return "\n".join(parts)


def _skill_epilogue_fallback_text(stats: dict[str, Any]) -> str:
    scen = str(stats.get("scenario") or "").strip() or "本次工勘"
    risk = int(stats.get("risk_rows") or 0)
    if risk > 0:
        return f"{scen}已顺利结案；尚有 {risk} 条遗留项建议纳入后续整改台账。"
    return f"{scen}已顺利结案，报告已分发，感谢您的投入与配合。"


async def _skill_epilogue_worker(
    *,
    thread_id: str,
    docman: Any,
    stats: dict[str, Any],
    card_id: str,
    agent_loop: Any,
) -> None:
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    text = ""
    provider = getattr(agent_loop, "provider", None) if agent_loop is not None else None
    if provider is not None:
        try:
            model = getattr(agent_loop, "model", None)
            resp = await provider.chat_with_retry(
                messages=[
                    {
                        "role": "system",
                        "content": "你是资深工勘顾问。只输出一句中文结案陈词：祝贺闭环并点出关键数字或下一步，不超过50字，不要 markdown、不要分点列表。",
                    },
                    {"role": "user", "content": _skill_epilogue_user_prompt(stats)},
                ],
                tools=None,
                model=model,
                max_tokens=160,
                temperature=0.45,
            )
            text = (resp.content or "").strip().replace("\n", " ")
        except Exception as e:
            logger.warning("skill.epilogue LLM failed | thread_id={} | {}", thread_id, e)
            text = ""
    if not text:
        text = _skill_epilogue_fallback_text(stats)
    if len(text) > 80:
        text = text[:80]
    try:
        await mc.emit_guidance(text, [], card_id=card_id)
    except Exception as e:
        logger.warning("skill.epilogue emit_guidance failed | thread_id={} | {}", thread_id, e)


async def emit_skill_runtime_event(
    *,
    envelope: dict[str, Any],
    thread_id: str,
    docman: Any = None,
    pending_hitl_store: Any = None,
    agent_loop: Any = None,
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
    if event == "skill.agent_task_execute":
        return await _emit_skill_agent_task_execute(
            envelope=envelope,
            payload=payload,
            thread_id=thread_id,
            agent_loop=agent_loop,
        )
    if event == "skill.epilogue":
        stats = payload.get("stats")
        if not isinstance(stats, dict):
            stats = {}
        cid = str(payload.get("cardId") or "zhgk:epilogue:final").strip() or "zhgk:epilogue:final"
        asyncio.create_task(
            _skill_epilogue_worker(
                thread_id=thread_id,
                docman=docman,
                stats=stats,
                card_id=cid,
                agent_loop=agent_loop,
            ),
            name="skill_epilogue",
        )
        return {"ok": True, "event": "skill.epilogue", "summary": "结案陈词已排队", "deferred": True}
    raise ValueError(f"unsupported skill runtime event: {event}")


def _tool_call_id_from_pending_payload(payload_json: str | None) -> str:
    if not isinstance(payload_json, str) or not payload_json.strip():
        return ""
    try:
        data = json.loads(payload_json)
        if isinstance(data, dict):
            return str(data.get("toolCallId") or "").strip()
    except json.JSONDecodeError:
        return ""
    return ""


def _upload_save_location_alias_from_pending_payload(payload_json: str | None) -> str:
    if not isinstance(payload_json, str) or not payload_json.strip():
        return ""
    try:
        data = json.loads(payload_json)
        if isinstance(data, dict):
            return str(data.get("saveLocationAlias") or "").strip()
    except json.JSONDecodeError:
        return ""
    return ""


def _desktop_subdir_from_pending_payload(payload_json: str | None) -> str:
    if not isinstance(payload_json, str) or not payload_json.strip():
        return ""
    try:
        data = json.loads(payload_json)
        if isinstance(data, dict):
            return str(data.get("desktopSubdir") or "").strip()
    except json.JSONDecodeError:
        return ""
    return ""


def _agui_workspace_root_fallback() -> Path:
    raw = str(os.environ.get("NANOBOT_AGUI_WORKSPACE") or os.environ.get("NANOBOT_AGUI_WORKSPACE_ROOT") or "").strip()
    if raw:
        try:
            return Path(os.path.expanduser(raw)).resolve()
        except Exception:
            pass
    return (Path.home() / ".nanobot" / "workspace").resolve()


def _safe_desktop_subdir(name: str) -> str:
    # Keep it simple: one folder name, no slashes or traversal.
    t = str(name or "").strip().strip("/\\")
    if not t:
        return ""
    if any(x in t for x in ("/", "\\", "..", ":")):
        return ""
    # Windows reserved chars
    bad = '\\/:*?"<>|'
    cleaned = "".join("_" if ch in bad else ch for ch in t)
    cleaned = " ".join(cleaned.split())
    return cleaned[:80]


def _try_copy_workspace_upload_to_desktop(*, resolved_result: Any, desktop_subdir: str) -> dict[str, Any] | None:
    """Best-effort: when agent upload targets Desktop, copy staged file to Desktop and return patched result.

    UI upload API is restricted to workspace-relative paths; we stage under workspace then copy out.
    """
    if not isinstance(resolved_result, dict):
        return None
    upload = resolved_result.get("upload")
    if not isinstance(upload, dict):
        return None
    logical = str(upload.get("logicalPath") or "").strip()
    if not logical:
        return None
    # Expect logicalPath like: workspace/uploads/temp/foo.xlsx
    p = logical.replace("\\", "/")
    if p.startswith("workspace/"):
        p = p[len("workspace/") :]
    ws_root = _agui_workspace_root_fallback()
    src = (ws_root / p).resolve()
    if not src.is_file():
        return None

    # Desktop path resolution (Windows/macOS/Linux best-effort)
    desktop_root = Path(os.path.expanduser("~/Desktop")).resolve()
    if not desktop_root.exists() or not desktop_root.is_dir():
        return None
    sub = _safe_desktop_subdir(desktop_subdir)
    desktop = (desktop_root / sub).resolve() if sub else desktop_root
    try:
        desktop.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    dst = (desktop / src.name).resolve()
    try:
        # Avoid overwrite by suffixing
        if dst.exists():
            stem = dst.stem
            suf = dst.suffix
            for i in range(2, 2000):
                cand = desktop / f"{stem} ({i}){suf}"
                if not cand.exists():
                    dst = cand.resolve()
                    break
        dst.write_bytes(src.read_bytes())
    except Exception:
        return None

    patched = dict(resolved_result)
    patched_upload = dict(upload)
    patched_upload["desktopPath"] = str(dst)
    if sub:
        patched_upload["desktopDir"] = str(desktop)
    patched["upload"] = patched_upload
    return patched


async def _persist_agent_upload_tool_result(
    *,
    session_manager: Any,
    session_key: str,
    tool_call_id: str,
    body: dict[str, Any],
) -> None:
    if session_manager is None or not (session_key or "").strip() or not (tool_call_id or "").strip():
        logger.warning(
            "agent_upload persist skipped | missing session_manager/session_key/tool_call_id | key={!r} tid={!r}",
            session_key,
            tool_call_id,
        )
        return
    session = session_manager.get_or_create(session_key)
    content = json.dumps(body, ensure_ascii=False)
    updated = False
    for msg in reversed(session.messages):
        if msg.get("role") == "tool" and str(msg.get("tool_call_id")) == tool_call_id:
            msg["content"] = content
            msg["name"] = "request_user_upload"
            updated = True
            break
    if not updated:
        session.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": "request_user_upload",
                "content": content,
                "timestamp": datetime.now().isoformat(),
            }
        )
    session.updated_at = datetime.now()
    session_manager.save(session)


async def dispatch_skill_runtime_intent(
    intent: dict[str, Any] | None,
    *,
    thread_id: str,
    docman: Any = None,
    pending_hitl_store: Any = None,
    resume_runner: Any = None,
    session_manager: Any = None,
    session_key: str | None = None,
    agent_loop: Any = None,
) -> tuple[bool, str]:
    if not intent:
        return False, ""

    verb = str(intent.get("verb") or "").strip()
    payload = intent.get("payload")
    if verb == "skill_runtime_start":
        if not isinstance(payload, dict):
            return True, "skill_runtime_start payload 非法"
        skill_name = str(payload.get("skillName") or "").strip()
        request_id = _ensure_unique_skill_runtime_start_request_id(payload)
        action = str(payload.get("action") or "").strip()
        tid = str(payload.get("threadId") or "").strip() or thread_id
        if not skill_name or not request_id or not action:
            return True, "skill_runtime_start 缺少必要字段（skillName/requestId/action）"
        if tid != thread_id:
            return True, "skill_runtime_start threadId 不匹配"
        if resume_runner is None:
            return True, "skill_runtime_start：resume_runner 未配置"

        # Switch right-side panel to this module (DashboardNavigator follows ModuleSessionFocus).
        try:
            from nanobot.agent.loop import emit_module_session_focus_event

            await emit_module_session_focus_event({"threadId": thread_id, "moduleId": skill_name, "status": "running"})
        except Exception:
            pass

        bootstrap = _try_load_skill_dashboard_bootstrap(skill_name)
        if bootstrap is not None:
            try:
                from nanobot.agent.loop import emit_skill_ui_bootstrap_event

                await emit_skill_ui_bootstrap_event(bootstrap)
            except Exception:
                # Best-effort: do not block skill execution on UI bootstrap.
                pass

        try:
            out = await resume_runner(
                thread_id=thread_id,
                skill_name=skill_name,
                request_id=request_id,
                action=action,
                status="ok",
                result={},
            )
        except Exception as e:
            logger.exception(
                "skill_runtime_start resume_runner raised | thread_id={} skill_name={} request_id={}",
                thread_id,
                skill_name,
                request_id,
            )
            return True, f"skill_runtime_start 异常：{type(e).__name__}: {e}"
        if isinstance(out, dict) and out.get("ok") is True:
            # Silent success: opening dashboards / starting skills should not pollute chat.
            return True, ""
        err = str((out or {}).get("error") or "").strip() if isinstance(out, dict) else ""
        return True, err or "skill_runtime_start 执行失败"
    if verb == "skill_runtime_event":
        if not isinstance(payload, dict):
            return True, "skill_runtime_event payload 非法"
        result = await emit_skill_runtime_event(
            envelope=payload,
            thread_id=thread_id,
            docman=docman,
            pending_hitl_store=pending_hitl_store,
            agent_loop=agent_loop,
        )
        if result.get("ok") is True:
            # UI updates arrive via SSE; do not mirror summary into RunFinished transcript.
            return True, ""
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

        try:
            out = await resume_runner(
                thread_id=thread_id,
                skill_name=skill_name,
                request_id=request_id,
                action=action,
                status=status,
                result=result_obj if result_obj is not None else {},
            )
        except Exception as e:
            logger.exception(
                "skill_runtime_resume resume_runner raised | thread_id={} skill_name={} request_id={}",
                thread_id,
                skill_name,
                request_id,
            )
            return True, f"skill_runtime_resume 异常：{type(e).__name__}: {e}"
        if isinstance(out, dict) and out.get("ok") is True:
            # Silent success: UI updates are delivered via SSE events (dashboard.patch/artifact.publish).
            # Avoid polluting the chat transcript with a completion line.
            return True, ""
        err = str((out or {}).get("error") or "").strip() if isinstance(out, dict) else ""
        return True, err or "skill_runtime_resume 执行失败"

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
        rid = str(payload.get("requestId") or "").strip()
        logger.info(
            "skill_runtime_result ingest | thread_id={} rid={} skill={} status={}",
            thread_id,
            rid,
            p_skill,
            p_status,
        )
        tool_call_id = ""
        upload_alias = ""
        desktop_subdir = ""
        if hasattr(pending_hitl_store, "get_pending_request"):
            pending_row = await pending_hitl_store.get_pending_request(rid)
            pj = None
            if isinstance(pending_row, dict):
                pj = pending_row.get("payload_json")
            tool_call_id = _tool_call_id_from_pending_payload(pj if isinstance(pj, str) else None)
            upload_alias = _upload_save_location_alias_from_pending_payload(pj if isinstance(pj, str) else None)
            desktop_subdir = _desktop_subdir_from_pending_payload(pj if isinstance(pj, str) else None)
        # Opportunistic zombie prevention: advance timeouts before consuming results.
        try:
            await pending_hitl_store.timeout_expired_requests()
        except Exception:
            # Timeout scan is best-effort; do not block result ingestion.
            pass
        try:
            out = await pending_hitl_store.consume_result(payload)
        except ValueError as e:
            # Store validation (e.g. rare races); return handled error instead of breaking /api/chat SSE.
            logger.warning(
                "skill_runtime_result consume failed | thread_id={} rid={} skill={} err={}",
                thread_id,
                rid,
                p_skill,
                e,
            )
            return True, f"skill_runtime_result: {e}"
        if out.get("ok") is True and out.get("duplicate") is True:
            logger.info(
                "skill_runtime_result duplicate (idempotent) | thread_id={} rid={} skill={}",
                thread_id,
                rid,
                p_skill,
            )
            return True, ""
        if out.get("ok") is not True:
            logger.warning(
                "skill_runtime_result consume not ok | thread_id={} rid={} skill={} out={}",
                thread_id,
                rid,
                p_skill,
                out,
            )
            return True, "skill_runtime_result 处理失败"

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

        if resolved_action == AGENT_UPLOAD_RESUME_ACTION:
            # If the user asked to save to Desktop, copy out after we have a durable workspace file.
            if upload_alias == "desktop":
                patched = _try_copy_workspace_upload_to_desktop(
                    resolved_result=resolved_result,
                    desktop_subdir=desktop_subdir,
                )
                if patched is not None:
                    resolved_result = patched
            sk = (session_key or "").strip() or str(thread_id)
            await _persist_agent_upload_tool_result(
                session_manager=session_manager,
                session_key=sk,
                tool_call_id=tool_call_id,
                body={
                    "ok": resolved_status == "ok",
                    "status": resolved_status,
                    "requestId": rid,
                    "result": resolved_result,
                },
            )
            return True, ""

        if resume_runner is None:
            logger.error(
                "skill_runtime_result consumed pending but resume_runner is None | thread_id={} rid={} skill={} action={}",
                thread_id,
                rid,
                p_skill,
                resolved_action,
            )
            return True, "skill_runtime_result：resume_runner 未配置，pending 已消费但无法续跑"

        ra = str(resolved_action or "").strip()
        if not ra:
            logger.error(
                "skill_runtime_result empty resolved_action after consume | thread_id={} rid={} skill={} replay={!r}",
                thread_id,
                rid,
                p_skill,
                replay,
            )
            return True, "skill_runtime_result：未能解析续跑 action（pending 或 replay 数据异常）"
        resolved_action = ra

        resume_skill = str(payload.get("skillName") or "").strip()
        try:
            resume_skill = get_skill_dir(resume_skill).name
        except Exception:
            pass

        logger.info(
            "skill_runtime_result resume_runner | thread_id={} rid={} resume_skill={} action={} status={}",
            thread_id,
            rid,
            resume_skill,
            resolved_action,
            resolved_status,
        )

        try:
            rr_out = await resume_runner(
                thread_id=str(payload.get("threadId") or "").strip(),
                skill_name=resume_skill,
                request_id=rid,
                action=resolved_action,
                status=resolved_status,
                result=resolved_result,
            )
        except Exception as e:
            logger.exception(
                "skill_runtime_result resume_runner raised | thread_id={} rid={} resume_skill={} action={}",
                thread_id,
                rid,
                resume_skill,
                resolved_action,
            )
            return True, f"skill_runtime_result 续跑异常：{type(e).__name__}: {e}"

        if isinstance(rr_out, dict) and rr_out.get("ok") is False:
            err = str(rr_out.get("error") or "").strip() or "续跑失败"
            logger.warning(
                "skill_runtime_result resume_runner returned ok=false | thread_id={} rid={} err={}",
                thread_id,
                rid,
                err,
            )
            return True, f"skill_runtime_result：{err}"

        return True, ""

    return False, ""
