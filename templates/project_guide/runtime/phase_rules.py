"""阶段判定纯函数。

职责（**只算不写**）：
- 解析 ``data/phases.json`` 单一真值表；
- 由 ``task_progress.json`` 的形态计算 ``order_cur``；
- 由 ``registry/project_members.json`` 的 ``stages[]`` + ``users.json`` 的 ``roleCode`` 计算 ``order_user`` / ``is_admin``；
- 输出三种分支（``wait`` / ``proceed`` / ``passed`` / ``admin`` / ``unknown``）+ 模板化文案 + 建议 CTA。

设计取舍：
- **不读文件**，调用方负责把 JSON 内容传进来；这样 driver / 测试 / 主 Agent / 后端钩子均可复用同一套逻辑。
- 阶段名做 *轻* 归一化（``strip`` + ``NFKC`` + 全/半角无关空格清理）以兼容 registry 里偶发的多余空白；不做模糊匹配，避免误判。
- ``decide_branch`` 输出与触发上下文相关的 ``transition`` 字段（若调用方提供），便于 UI 渲染「{from} 已完成 → 进入 {to}」。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any


def _norm(s: Any) -> str:
    if s is None:
        return ""
    raw = str(s)
    nfkc = unicodedata.normalize("NFKC", raw)
    return "".join(nfkc.split())


@dataclass(frozen=True)
class Phase:
    order: int
    display_name: str
    module_id: str
    skill_dir: str
    aliases: tuple[str, ...] = ()


def load_phases(phases_doc: dict[str, Any]) -> list[Phase]:
    """从已解析的 ``phases.json`` 字典构造有序 ``Phase`` 列表。

    - 强制按 ``order`` 升序、连续从 0 开始（不连续会抛 ``ValueError``，避免静默漂移）。
    - ``displayName`` / ``moduleId`` / ``skillDir`` 必填。
    """
    items = phases_doc.get("phases") if isinstance(phases_doc, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("phases.json 缺少 phases[] 或为空")

    phases: list[Phase] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError(f"phases[] 条目非对象：{raw!r}")
        order = raw.get("order")
        display_name = raw.get("displayName")
        module_id = raw.get("moduleId")
        skill_dir = raw.get("skillDir")
        if not isinstance(order, int):
            raise ValueError(f"phase.order 必须为 int：{raw!r}")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(f"phase.displayName 必填：{raw!r}")
        if not isinstance(module_id, str) or not module_id.strip():
            raise ValueError(f"phase.moduleId 必填：{raw!r}")
        if not isinstance(skill_dir, str) or not skill_dir.strip():
            raise ValueError(f"phase.skillDir 必填：{raw!r}")
        aliases_raw = raw.get("aliases") or []
        aliases = tuple(str(a) for a in aliases_raw if isinstance(a, str))
        phases.append(
            Phase(
                order=order,
                display_name=display_name.strip(),
                module_id=module_id.strip(),
                skill_dir=skill_dir.strip(),
                aliases=aliases,
            )
        )

    phases.sort(key=lambda p: p.order)
    for idx, p in enumerate(phases):
        if p.order != idx:
            raise ValueError(
                f"phases[].order 必须从 0 起连续递增；位置 {idx} 拿到 order={p.order}"
            )
    return phases


def _phase_completed(progress_entry: dict[str, Any]) -> bool:
    """阶段完成 = ``tasks[]`` 全部 ``completed: true``。空 tasks 视为未完成（保守）。"""
    tasks = progress_entry.get("tasks") if isinstance(progress_entry, dict) else None
    if not isinstance(tasks, list) or not tasks:
        return False
    for t in tasks:
        if not isinstance(t, dict):
            return False
        if not bool(t.get("completed")):
            return False
    return True


def compute_order_cur(task_progress: dict[str, Any], phases: list[Phase]) -> int:
    """全局焦点：``phases`` 中**第一个未完成**阶段的 ``order``。

    - 若 ``task_progress`` 中找不到某 phase 的条目，按"未完成"处理。
    - 若所有阶段都完成 → 返回 ``len(phases)``（"全部完成"哨兵值）。
    """
    progress = task_progress.get("progress") if isinstance(task_progress, dict) else None
    by_module: dict[str, dict[str, Any]] = {}
    if isinstance(progress, list):
        for entry in progress:
            if not isinstance(entry, dict):
                continue
            mid = entry.get("moduleId")
            if isinstance(mid, str):
                by_module[mid.strip()] = entry

    for p in phases:
        entry = by_module.get(p.module_id)
        if not entry or not _phase_completed(entry):
            return p.order
    return len(phases)


def compute_order_user(member_stages: list[Any] | None, phases: list[Phase]) -> int | None:
    """用户主阶段：``member_stages`` 中能命中某 phase 的项里 ``order`` 最小者。

    - 命中规则：归一化（``NFKC`` + 去空格）后 == phase.displayName 归一化。
    - 命中不到 → 返回 ``None``（调用方按"未知/兜底"处理）。
    """
    if not isinstance(member_stages, list) or not member_stages:
        return None
    by_norm: dict[str, Phase] = {_norm(p.display_name): p for p in phases}
    found: list[int] = []
    for s in member_stages:
        key = _norm(s)
        if not key:
            continue
        p = by_norm.get(key)
        if p is not None:
            found.append(p.order)
    if not found:
        return None
    return min(found)


def is_admin_role(role_code: Any, phases_doc: dict[str, Any] | None = None) -> bool:
    admin_codes = {"ADMIN"}
    if isinstance(phases_doc, dict):
        cfg = phases_doc.get("admin")
        if isinstance(cfg, dict):
            roles = cfg.get("roleCodes")
            if isinstance(roles, list):
                admin_codes = {str(r).strip().upper() for r in roles if isinstance(r, str)}
    return isinstance(role_code, str) and role_code.strip().upper() in admin_codes


@dataclass(frozen=True)
class GuideDecision:
    """引导 SKILL 的结构化输出。

    - ``branch`` ∈ {``wait``, ``proceed``, ``passed``, ``admin``, ``done``, ``unknown``}
    - ``cur_phase`` / ``user_phase`` 任一可能为 ``None``
    - ``cta`` 为 ``None`` 表示「不要给用户主流程 CTA」
    """

    branch: str
    cur_phase: Phase | None
    user_phase: Phase | None
    headline: str
    body: str
    cta: dict[str, str] | None
    transition_id: str | None


def _phase_or_none(phases: list[Phase], order: int | None) -> Phase | None:
    if order is None:
        return None
    if 0 <= order < len(phases):
        return phases[order]
    return None


def decide_branch(
    *,
    phases: list[Phase],
    order_cur: int,
    order_user: int | None,
    is_admin: bool = False,
    member_role: str | None = None,
    transition: dict[str, Any] | None = None,
    task_progress: dict[str, Any] | None = None,
) -> GuideDecision:
    """合成话术 + CTA。文案为模板化中文短句，前端可直接展示或交由主 Agent 重写口吻。"""
    cur = _phase_or_none(phases, order_cur)
    user = _phase_or_none(phases, order_user)

    transition_id: str | None = None
    transition_prefix = ""
    if isinstance(transition, dict):
        from_id = transition.get("from_module")
        to_id = transition.get("to_module")
        if isinstance(from_id, str) and isinstance(to_id, str):
            updated_at = ""
            if isinstance(task_progress, dict):
                updated_at = str(task_progress.get("updatedAt") or "")
            transition_id = f"{from_id}->{to_id}@{updated_at}"
            from_phase = next((p for p in phases if p.module_id == from_id), None)
            to_phase = next((p for p in phases if p.module_id == to_id), None)
            if from_phase and to_phase:
                transition_prefix = f"{from_phase.display_name} 已完成 ✅，下一阶段：{to_phase.display_name}。"

    if order_cur >= len(phases):
        return GuideDecision(
            branch="done",
            cur_phase=None,
            user_phase=user,
            headline="全部阶段已完成",
            body="所有阶段任务都已闭环，可进入复盘或归档。",
            cta=None,
            transition_id=transition_id,
        )

    if is_admin:
        assert cur is not None
        return GuideDecision(
            branch="admin",
            cur_phase=cur,
            user_phase=user,
            headline=f"{transition_prefix}当前阶段：{cur.display_name}",
            body=f"管理员视角：可直接进入 {cur.display_name}，或查看任意阶段。",
            cta={"action": "skill_runtime_start", "skillDir": cur.skill_dir},
            transition_id=transition_id,
        )

    if (member_role or "").strip().lower() == "viewer":
        assert cur is not None
        return GuideDecision(
            branch="wait",
            cur_phase=cur,
            user_phase=user,
            headline=f"{transition_prefix}当前阶段：{cur.display_name}",
            body=f"你是只读成员（viewer），可查看进度但不发起主流程操作。",
            cta=None,
            transition_id=transition_id,
        )

    if user is None:
        assert cur is not None
        return GuideDecision(
            branch="unknown",
            cur_phase=cur,
            user_phase=None,
            headline=f"{transition_prefix}当前阶段：{cur.display_name}",
            body="未在项目成员表中找到你的阶段角色，请联系管理员配置 stages 后再操作。",
            cta=None,
            transition_id=transition_id,
        )

    assert cur is not None and user is not None
    if order_user > order_cur:
        return GuideDecision(
            branch="wait",
            cur_phase=cur,
            user_phase=user,
            headline=f"{transition_prefix}当前阶段：{cur.display_name}",
            body=(
                f"你负责的是「{user.display_name}」，但流程仍在「{cur.display_name}」，"
                "请等待前序阶段完成后再开始。"
            ),
            cta=None,
            transition_id=transition_id,
        )

    if order_user < order_cur:
        return GuideDecision(
            branch="passed",
            cur_phase=cur,
            user_phase=user,
            headline=f"{transition_prefix}当前阶段：{cur.display_name}",
            body=(
                f"你负责的「{user.display_name}」阶段已结束，当前已进入「{cur.display_name}」，"
                "可进入只读/复盘视图。"
            ),
            cta=None,
            transition_id=transition_id,
        )

    return GuideDecision(
        branch="proceed",
        cur_phase=cur,
        user_phase=user,
        headline=f"{transition_prefix}轮到你了：{cur.display_name}",
        body=f"现在进入「{cur.display_name}」阶段，可在工作台启动 {cur.skill_dir} SKILL 继续推进。",
        cta={"action": "skill_runtime_start", "skillDir": cur.skill_dir},
        transition_id=transition_id,
    )


def make_phase_guide_handoff_event(
    *,
    thread_id: str,
    skill_run_id: str,
    timestamp_ms: int,
    from_module: str,
    to_module: str | None,
    task_progress_updated_at: str = "",
) -> dict[str, Any]:
    """构造三阶段 SKILL 收尾时**触发 project_guide** 的事件载荷。

    用法（业务 driver 收尾处）::

        _print_event(make_phase_guide_handoff_event(
            thread_id=thread_id,
            skill_run_id=run_id,
            timestamp_ms=_now_ms(),
            from_module="job_management",
            to_module="smart_survey",
            task_progress_updated_at=_iso_now(),
        ))

    集中在此处的好处：
    - 三个业务 driver 调用同一份 schema，避免各自抄一遍；
    - ``transition_id`` 生成规则唯一，前端/后端做幂等不会算错；
    - 后续修改事件结构（如增字段、改 event 名）只动一处。
    """
    transition_id = f"{from_module}->{to_module or '∅'}@{task_progress_updated_at}"
    return {
        "event": "skill_runtime_start",
        "threadId": thread_id,
        "skillRunId": skill_run_id,
        "timestamp": timestamp_ms,
        "payload": {
            "skillName": "project_guide",
            "action": "guide_next_phase",
            "transition": {
                "from_module": from_module,
                "to_module": to_module,
            },
            "transition_id": transition_id,
        },
    }


__all__ = [
    "Phase",
    "GuideDecision",
    "load_phases",
    "compute_order_cur",
    "compute_order_user",
    "is_admin_role",
    "decide_branch",
    "make_phase_guide_handoff_event",
]
