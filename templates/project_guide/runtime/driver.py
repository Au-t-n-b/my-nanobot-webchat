"""项目阶段引导（project_guide）Skill-First 驱动。

设计取舍：
- **零外部依赖**：driver 在子进程跑，import 路径上只能看到自己目录；除标准库外仅依赖
  同目录的 ``phase_rules`` 纯函数（``run_skill_runtime_driver`` 把 cwd 设到 skill_dir）。
- **永不 raise 出 main**：任何 I/O 或解析错误都打 stderr，并输出兜底 ``chat.guidance``
  事件，让 resume_runner 仍以 ok 回到前端，前端能看到"配置缺失"提示而不是空白。
- **不写文件、不修改 task_progress**：本 skill 只读、只渲染；写进展由三阶段 driver 负责。

stdin/stdout 协议见 ``nanobot.web.skill_runtime_driver.run_skill_runtime_driver``：
    request = {thread_id, skill_name, request_id, action, status, result}
    本 driver 关心的 request.result 字段：
        - userId / workId        登录用户身份；缺则按 users.lastLoginAt 兜底
        - projectId              定位 project_members 行；缺则取该用户的第一个项目
        - transition             {from_module, to_module}（来自三阶段收尾 handoff）
        - transition_id          幂等键；缺则由 decide_branch 内部推断
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

# phase_rules 与本文件同目录；run_skill_runtime_driver 把 cwd 设到 skill_dir，
# 但插入 __file__ 的目录到 sys.path 更稳（兼容直接 ``python driver.py`` 的本地调试）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_rules  # noqa: E402


def _log(msg: str) -> None:
    """stderr trace；不污染 stdout 事件流。"""
    print(f"[project_guide.driver] {msg}", file=sys.stderr, flush=True)


def _emit(envelope: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _as_str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _log(f"file not found: {path}")
    except Exception as e:
        _log(f"read {path} failed: {type(e).__name__}: {e}")
    return None


def _resolve_user(
    *,
    users_doc: dict[str, Any] | None,
    hint_user_id: str,
    hint_employee_no: str,
) -> dict[str, Any] | None:
    """三阶兜底锁定当前用户：userId → employeeNo → 最近登录者。

    显式 hint 命中是首选；fallback 仅用于演示场景（很多本地会话不带身份）。
    """
    users = (users_doc or {}).get("users") if isinstance(users_doc, dict) else None
    if not isinstance(users, list):
        return None
    by_id: dict[str, dict[str, Any]] = {}
    by_emp: dict[str, dict[str, Any]] = {}
    for u in users:
        if not isinstance(u, dict):
            continue
        uid = _as_str(u.get("id"))
        emp = _as_str(u.get("employeeNo"))
        if uid:
            by_id[uid] = u
        if emp:
            by_emp[emp] = u
    if hint_user_id and hint_user_id in by_id:
        return by_id[hint_user_id]
    if hint_employee_no and hint_employee_no in by_emp:
        return by_emp[hint_employee_no]
    candidates = [u for u in users if isinstance(u, dict) and u.get("lastLoginAt")]
    if not candidates:
        return None
    # ISO-8601 字典序 == 时间序，安全地拿"最近登录者"
    candidates.sort(key=lambda u: _as_str(u.get("lastLoginAt")), reverse=True)
    return candidates[0]


def _resolve_member_row(
    *,
    members_doc: dict[str, Any] | None,
    user_id: str,
    hint_project_id: str,
) -> dict[str, Any] | None:
    members = (members_doc or {}).get("members") if isinstance(members_doc, dict) else None
    if not isinstance(members, list) or not user_id:
        return None
    matches = [
        m for m in members
        if isinstance(m, dict) and _as_str(m.get("userId")) == user_id
    ]
    if not matches:
        return None
    if hint_project_id:
        for m in matches:
            if _as_str(m.get("projectId")) == hint_project_id:
                return m
    return matches[0]


def _start_intent_payload_for_phase(
    *,
    phases_doc: dict[str, Any],
    skill_dir: str,
    thread_id: str,
) -> dict[str, Any] | None:
    """从 phases.json 查 startAction / startRequestId 构造 skill_runtime_start payload。

    配置不全（缺 startAction）就返回 None，让 caller 不渲染按钮，
    避免推一个会被后端拒绝的坏 intent。
    """
    phases = phases_doc.get("phases") if isinstance(phases_doc, dict) else None
    if not isinstance(phases, list):
        return None
    for p in phases:
        if not isinstance(p, dict):
            continue
        if _as_str(p.get("skillDir")) != skill_dir:
            continue
        start_action = _as_str(p.get("startAction"))
        if not start_action:
            return None
        start_request_id = _as_str(p.get("startRequestId")) or f"req-start-{skill_dir}"
        return {
            "type": "skill_runtime_start",
            "skillName": skill_dir,
            "requestId": start_request_id,
            "action": start_action,
            "threadId": thread_id,
        }
    return None


def _build_guidance_actions(
    *,
    decision: "phase_rules.GuideDecision",
    phases_doc: dict[str, Any],
    thread_id: str,
) -> list[dict[str, Any]]:
    cta = decision.cta
    if not cta or cta.get("action") != "skill_runtime_start":
        return []
    skill_dir = _as_str(cta.get("skillDir"))
    if not skill_dir:
        return []
    payload = _start_intent_payload_for_phase(
        phases_doc=phases_doc,
        skill_dir=skill_dir,
        thread_id=thread_id,
    )
    if payload is None:
        return []
    label_phase = decision.cur_phase.display_name if decision.cur_phase else skill_dir
    return [
        {
            "label": f"启动「{label_phase}」",
            "verb": "skill_runtime_start",
            "payload": payload,
        }
    ]


def _emit_guidance(
    *,
    decision: "phase_rules.GuideDecision",
    phases_doc: dict[str, Any],
    thread_id: str,
    transition_id: str | None,
) -> None:
    context_parts = [decision.headline.strip(), decision.body.strip()]
    context = "\n\n".join(part for part in context_parts if part)
    actions = _build_guidance_actions(
        decision=decision,
        phases_doc=phases_doc,
        thread_id=thread_id,
    )
    # 稳定 cardId：同 thread 同 transition_id 重发会替换上一张卡，避免堆叠重复引导。
    cid_seed = transition_id or "cold"
    payload: dict[str, Any] = {
        "context": context,
        "actions": actions,
        "cardId": f"project_guide:{thread_id}:{cid_seed}",
    }
    _emit({"event": "chat.guidance", "payload": payload})


def _fallback_guidance(thread_id: str, reason: str) -> None:
    _emit(
        {
            "event": "chat.guidance",
            "payload": {
                "context": f"引导加载失败，请检查工作区配置。\n（{reason}）",
                "actions": [],
                "cardId": f"project_guide:{thread_id}:fallback",
            },
        }
    )


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    try:
        obj = json.loads(raw or "{}")
    except Exception as e:
        _log(f"stdin not JSON: {e}; raw_head={raw[:200]!r}")
        return {}
    return obj if isinstance(obj, dict) else {}


def main() -> int:
    req = _read_request()
    thread_id = _as_str(req.get("thread_id")) or "unknown"
    result = req.get("result")
    if not isinstance(result, dict):
        result = {}

    # cwd = <workspace>/skills/<this-skill>/   →  workspace_root = skill_dir.parents[1]
    skill_dir = Path(__file__).resolve().parent.parent
    workspace_root = skill_dir.parent.parent
    _log(f"thread_id={thread_id} skill_dir={skill_dir} workspace_root={workspace_root}")

    phases_doc = _read_json(skill_dir / "data" / "phases.json")
    if not isinstance(phases_doc, dict):
        _fallback_guidance(thread_id, "phases.json 缺失或非法 JSON")
        return 0

    try:
        phases = phase_rules.load_phases(phases_doc)
    except Exception as e:
        _log(f"load_phases failed: {e}\n{traceback.format_exc()}")
        _fallback_guidance(thread_id, f"phases.json 解析失败：{e}")
        return 0

    task_progress = _read_json(workspace_root / "task_progress.json") or {}
    users_doc = _read_json(workspace_root / "registry" / "users.json")
    members_doc = _read_json(workspace_root / "registry" / "project_members.json")

    user = _resolve_user(
        users_doc=users_doc,
        hint_user_id=_as_str(result.get("userId")),
        hint_employee_no=_as_str(result.get("workId")) or _as_str(result.get("employeeNo")),
    )
    if user is None:
        _log("could not resolve current user (no registry / no lastLoginAt)")

    user_id = _as_str((user or {}).get("id"))
    role_code = _as_str((user or {}).get("roleCode"))
    member_row = (
        _resolve_member_row(
            members_doc=members_doc,
            user_id=user_id,
            hint_project_id=_as_str(result.get("projectId")),
        )
        if user_id
        else None
    )
    member_stages = member_row.get("stages") if isinstance(member_row, dict) else None
    member_role = _as_str(member_row.get("memberRole")) if isinstance(member_row, dict) else None

    try:
        order_cur = phase_rules.compute_order_cur(task_progress, phases)
        order_user = phase_rules.compute_order_user(member_stages, phases)
        is_admin = phase_rules.is_admin_role(role_code, phases_doc)
    except Exception as e:
        _log(f"derive failed: {e}\n{traceback.format_exc()}")
        _fallback_guidance(thread_id, f"派生量计算失败：{e}")
        return 0

    raw_tr = result.get("transition")
    transition = raw_tr if isinstance(raw_tr, dict) else None

    try:
        decision = phase_rules.decide_branch(
            phases=phases,
            order_cur=order_cur,
            order_user=order_user,
            is_admin=is_admin,
            member_role=member_role,
            transition=transition,
            task_progress=task_progress,
        )
    except Exception as e:
        _log(f"decide_branch failed: {e}\n{traceback.format_exc()}")
        _fallback_guidance(thread_id, f"分支判定失败：{e}")
        return 0

    # 优先使用调用方传入的 transition_id（三阶段 driver handoff），否则用 decision 内推断的。
    explicit_tid = _as_str(result.get("transition_id"))
    transition_id = explicit_tid or decision.transition_id

    _log(
        f"decision branch={decision.branch} order_cur={order_cur} order_user={order_user} "
        f"is_admin={is_admin} member_role={member_role!r} user_id={user_id!r} "
        f"transition_id={transition_id!r}"
    )
    _emit_guidance(
        decision=decision,
        phases_doc=phases_doc,
        thread_id=thread_id,
        transition_id=transition_id,
    )
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        _log(f"unhandled: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        try:
            _fallback_guidance("unknown", f"{type(e).__name__}: {e}")
        except Exception:
            pass
        rc = 0
    raise SystemExit(rc)
