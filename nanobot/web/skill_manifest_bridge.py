"""Bridge declarative skill manifests into existing chat-card HITL flows."""

from __future__ import annotations

import json
from typing import Any

from nanobot.skills.manifest_loader import load_skill_manifest
from nanobot.skills.manifest_runtime import run_manifest_step
from nanobot.web.mission_control import MissionControlManager

_MANIFEST_SESSIONS: dict[tuple[str, str], dict[str, Any]] = {}


def _session_key(thread_id: str, state_namespace: str) -> tuple[str, str]:
    return (str(thread_id or "").strip(), str(state_namespace or "").strip())


def _load_session(thread_id: str, state_namespace: str) -> dict[str, Any]:
    payload = _MANIFEST_SESSIONS.get(_session_key(thread_id, state_namespace))
    if not isinstance(payload, dict):
        return {"currentStep": "", "state": {}}
    state = payload.get("state")
    return {
        "currentStep": str(payload.get("currentStep") or "").strip(),
        "state": dict(state) if isinstance(state, dict) else {},
    }


def _save_session(
    thread_id: str,
    state_namespace: str,
    *,
    current_step: str,
    state: dict[str, Any],
) -> None:
    _MANIFEST_SESSIONS[_session_key(thread_id, state_namespace)] = {
        "currentStep": str(current_step or "").strip(),
        "state": dict(state),
    }


def _clear_session(thread_id: str, state_namespace: str) -> None:
    _MANIFEST_SESSIONS.pop(_session_key(thread_id, state_namespace), None)


def _manifest_card_id(state_namespace: str, step_id: str) -> str:
    return f"skill-manifest:{state_namespace}:{step_id}"


def _manifest_has_step(manifest: Any, step_id: str) -> bool:
    try:
        manifest.step_by_id(step_id)
        return True
    except KeyError:
        return False


async def _emit_blocked_step(
    *,
    mc: MissionControlManager,
    skill_name: str,
    state_namespace: str,
    step_result: dict[str, Any],
) -> None:
    step_id = str(step_result.get("stepId") or "").strip()
    step_type = str(step_result.get("stepType") or "").strip()
    if step_type == "file_gate":
        upload = step_result.get("upload") if isinstance(step_result.get("upload"), dict) else {}
        await mc.ask_for_file(
            purpose=f"skill-manifest:{skill_name}:{step_id}",
            title=str(step_result.get("title") or "请上传文件"),
            accept=str(upload.get("accept") or "").strip() or None,
            multiple=bool(upload.get("multiple")),
            mode="replace",
            card_id=_manifest_card_id(state_namespace, step_id),
            save_relative_dir=str(upload.get("saveDir") or "").strip() or None,
            skill_name=skill_name,
            state_namespace=state_namespace,
            step_id=step_id,
        )
        return

    if step_type == "choice_gate":
        raw_options = step_result.get("options") if isinstance(step_result.get("options"), list) else []
        options = [dict(item) for item in raw_options if isinstance(item, dict)]
        await mc.emit_choices(
            str(step_result.get("title") or "请选择"),
            options,
            card_id=_manifest_card_id(state_namespace, step_id),
            skill_name=skill_name,
            state_namespace=state_namespace,
            step_id=step_id,
        )
        return

    raise ValueError(f"unsupported blocked manifest step type: {step_type}")


async def run_skill_manifest_action(
    *,
    skill_name: str,
    action: str,
    thread_id: str,
    docman: Any = None,
    step_id: str = "",
    state_namespace: str = "",
    state: dict[str, Any] | None = None,
    input_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = load_skill_manifest(skill_name)
    namespace = str(state_namespace or manifest.state_namespace).strip() or manifest.state_namespace
    session = _load_session(thread_id, namespace)
    session_state = dict(session.get("state") or {})
    if isinstance(state, dict):
        session_state.update(state)

    act = str(action or "").strip() or "guide"
    if act == "cancel":
        _clear_session(thread_id, namespace)
        return {"ok": True, "summary": "已取消当前技能引导。"}

    current_step = ""
    if act == "guide":
        session_state = dict(state or {})
        current_step = manifest.entry
    else:
        current_step = str(step_id or session.get("currentStep") or manifest.entry).strip() or manifest.entry

    mc = MissionControlManager(thread_id=thread_id, docman=docman)

    for _ in range(len(manifest.steps) + 1):
        result = run_manifest_step(
            manifest=manifest,
            step_id=current_step,
            state=session_state,
            input_data=input_data,
        )
        if result.get("status") == "blocked_by_hitl":
            _save_session(
                thread_id,
                namespace,
                current_step=str(result.get("stepId") or current_step),
                state=dict(result.get("state") or session_state),
            )
            await _emit_blocked_step(
                mc=mc,
                skill_name=skill_name,
                state_namespace=namespace,
                step_result=result,
            )
            return {
                "ok": True,
                "status": "blocked_by_hitl",
                "stepId": str(result.get("stepId") or current_step),
                "state": dict(result.get("state") or session_state),
            }

        if result.get("status") != "completed":
            raise ValueError(f"unsupported manifest runtime status: {result.get('status')}")

        session_state = dict(result.get("state") or session_state)
        next_step = str(result.get("next") or "").strip()
        _save_session(thread_id, namespace, current_step=next_step, state=session_state)
        if next_step and _manifest_has_step(manifest, next_step):
            current_step = next_step
            input_data = None
            continue

        summary = str(result.get("summary") or "").strip()
        if not summary:
            summary = "已完成技能输入准备。"
        return {
            "ok": True,
            "status": "completed",
            "next": next_step,
            "state": session_state,
            "summary": summary,
        }

    raise RuntimeError("manifest execution exceeded step limit")


def _parse_skill_manifest_payload(
    payload: Any,
) -> tuple[str, str, str, dict[str, Any], dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None
    skill_name = str(payload.get("skillName") or "").strip()
    action = str(payload.get("action") or "").strip()
    step_id = str(payload.get("stepId") or "").strip()
    raw_state = payload.get("state")
    raw_input = payload.get("inputData")
    state = dict(raw_state) if isinstance(raw_state, dict) else {}
    input_data = dict(raw_input) if isinstance(raw_input, dict) else {}
    if not skill_name or not action:
        return None
    return skill_name, action, step_id, state, input_data


async def dispatch_skill_manifest_intent(
    intent: dict[str, Any] | None,
    *,
    thread_id: str,
    docman: Any = None,
) -> tuple[bool, str]:
    if not intent:
        return False, ""

    verb = str(intent.get("verb") or "").strip()
    payload = intent.get("payload")

    if verb == "skill_manifest_action":
        parsed = _parse_skill_manifest_payload(payload)
        if not parsed:
            return True, json.dumps({"ok": False, "error": "invalid skill_manifest_action payload"}, ensure_ascii=False)
        skill_name, action, step_id, state, input_data = parsed
        result = await run_skill_manifest_action(
            skill_name=skill_name,
            action=action,
            thread_id=thread_id,
            docman=docman,
            step_id=step_id,
            state_namespace=str((payload or {}).get("stateNamespace") or "").strip(),
            state=state,
            input_data=input_data,
        )
        if result.get("ok") is True:
            return True, str(result.get("summary") or "").strip()
        return True, str(result.get("error") or "操作失败").strip()

    if verb == "choice_selected" and isinstance(payload, dict):
        skill_name = str(payload.get("skillName") or "").strip()
        if not skill_name:
            return False, ""
        result = await run_skill_manifest_action(
            skill_name=skill_name,
            action="resume",
            thread_id=thread_id,
            docman=docman,
            step_id=str(payload.get("stepId") or "").strip(),
            state_namespace=str(payload.get("stateNamespace") or "").strip(),
            input_data={"optionId": str(payload.get("optionId") or "").strip()},
        )
        if result.get("ok") is True:
            return True, str(result.get("summary") or "").strip()
        return True, str(result.get("error") or "操作失败").strip()

    return False, ""
