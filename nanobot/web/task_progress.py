"""Shared helpers for project-level task progress payloads."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


def task_progress_file_path() -> Path:
    """Persist ``task_progress.json`` under the user workspace (``~/.nanobot/workspace/`` by default).

    * ``NANOBOT_TASK_PROGRESS_FILE`` — full path to the JSON file (tests, overrides).
    """
    p = (os.environ.get("NANOBOT_TASK_PROGRESS_FILE") or "").strip()
    if p:
        return Path(p)
    return Path.home() / ".nanobot" / "workspace" / "task_progress.json"


def _tasks(names: list[str]) -> list[dict[str, Any]]:
    return [{"name": n, "completed": False} for n in names]


def default_task_progress_file_payload() -> dict[str, Any]:
    """Six high-level delivery phases; ``moduleId`` values match frontend :func:`composeProjectRegistryItems`."""
    return {
        "schemaVersion": 1,
        "updatedAt": None,
        "progress": [
            {
                "moduleId": "job_management",
                "moduleName": "作业管理",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "作业待启动",
                        "资料已上传",
                        "规划设计排期已确认",
                        "工程安装排期已确认",
                        "集群联调排期已确认",
                        "作业闭环完成",
                    ],
                ),
            },
            {
                "moduleId": "smart_survey",
                "moduleName": "智慧工勘",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "场景筛选与底表过滤",
                        "勘测数据汇总",
                        "报告生成",
                        "审批与分发闭环",
                    ],
                ),
            },
            {
                # ``moduleId`` 与 ``templates/project_guide/data/phases.json`` 中
                # 该阶段的 ``moduleId`` 保持一致；jmfz driver 发出的 ``task_progress.sync``
                # 也使用此 ID，避免 ``merge_task_progress_sync_to_disk`` 找不到模块而跳过。
                "moduleId": "modeling_simulation_workbench",
                "moduleName": "建模仿真",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "BOQ 提取",
                        "设备确认",
                        "创建设备",
                        "拓扑确认",
                        "拓扑连接",
                    ],
                ),
            },
            {
                "moduleId": "system_design",
                "moduleName": "系统设计",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "需求与范围基线",
                        "方案与架构评审",
                        "设计基线冻结",
                        "变更与风险登记",
                    ],
                ),
            },
            {
                "moduleId": "device_install",
                "moduleName": "设备安装",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "进场与验货",
                        "安装与上电",
                        "单机自检",
                        "系统联线",
                        "安规与资产标签",
                    ],
                ),
            },
            {
                "moduleId": "sw_deploy_commission",
                "moduleName": "软件部署与调测",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "环境基线",
                        "应用与中间件部署",
                        "联调对点",
                        "性能与稳定验证",
                        "移交与培训",
                    ],
                ),
            },
        ],
    }


def normalize_task_progress_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted progress data into the frontend's task-status shape."""
    if "modules" in payload and "overall" in payload:
        modules = payload.get("modules")
        if not isinstance(modules, list):
            modules = []
        else:
            # Same dedup as the ``progress`` branch below — driver-direct payloads
            # (e.g. ``task_progress.sync``) usually carry 1–2 modules, but a stale
            # cache or malformed event must not surface duplicate ``id`` to the
            # frontend stepper.
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for m in modules:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "").strip()
                if mid and mid in seen:
                    continue
                if mid:
                    seen.add(mid)
                unique.append(m)
            if len(unique) != len(modules):
                modules = unique
                payload["modules"] = unique
        if "summary" not in payload:
            active_count = sum(1 for module in modules if module.get("status") == "running")
            completed_count = sum(1 for module in modules if module.get("status") == "completed")
            failed_count = sum(1 for module in modules if module.get("status") == "failed")
            skipped_count = sum(1 for module in modules if module.get("status") == "skipped")
            pending_count = sum(1 for module in modules if module.get("status") == "pending")
            total_count = len(modules)
            remainder = total_count - active_count - completed_count - pending_count - failed_count - skipped_count
            if remainder > 0:
                pending_count += remainder
            payload["summary"] = {
                "activeCount": active_count,
                "pendingCount": pending_count,
                "completedCount": completed_count,
                "completionRate": round((completed_count / total_count) * 100) if total_count else 0,
            }
        return payload

    progress = payload.get("progress")
    if not isinstance(progress, list):
        progress = []

    modules: list[dict[str, Any]] = []
    # 防御性去重：``progress[]`` 里若同 ``moduleId`` 出现多次（旧版本 jmfz driver 的 ``moduleId``
    # 由 ``jmfz`` 改名为 ``modeling_simulation_workbench`` 时会产生此类历史脏数据），
    # 仅保留**首条**，避免下游 ``modules[].id`` 重复让前端 stepper 的 ``key`` 冲突崩 React。
    seen_module_ids: set[str] = set()
    for mod_index, raw_module in enumerate(progress, start=1):
        module_id = str(raw_module.get("moduleId") or f"m_{mod_index}")
        if module_id in seen_module_ids:
            continue
        seen_module_ids.add(module_id)
        module_name = str(raw_module.get("moduleName") or module_id)
        raw_tasks = raw_module.get("tasks")
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        steps: list[dict[str, Any]] = []
        completed_count = 0
        for task_index, raw_task in enumerate(raw_tasks, start=1):
            done = bool(raw_task.get("completed"))
            if done:
                completed_count += 1
            steps.append(
                {
                    "id": f"{module_id}_s_{task_index}",
                    "name": str(raw_task.get("name") or f"任务 {task_index}"),
                    "done": done,
                }
            )

        if steps and completed_count == len(steps):
            status = "completed"
        elif completed_count > 0:
            status = "running"
        else:
            status = "pending"

        modules.append(
            {
                "id": module_id,
                "name": module_name,
                "status": status,
                "steps": steps,
            }
        )

    done_count = sum(1 for module in modules if module["status"] == "completed")
    active_count = sum(1 for module in modules if module["status"] == "running")
    pending_count = sum(1 for module in modules if module["status"] == "pending")
    return {
        "updatedAt": payload.get("updatedAt"),
        "overall": {"doneCount": done_count, "totalCount": len(modules)},
        "summary": {
            "activeCount": active_count,
            "pendingCount": pending_count,
            "completedCount": done_count,
            "completionRate": round((done_count / len(modules)) * 100) if modules else 0,
        },
        "modules": modules,
    }


def _job_management_ui_state_path() -> Path:
    return (
        Path.home()
        / ".nanobot"
        / "workspace"
        / "skills"
        / "job_management"
        / "ProjectData"
        / "RunTime"
        / "ui_state.json"
    )


def _coerce_done_from_flow_item(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    if status in {"done", "completed", "complete", "success"}:
        return True
    pct = item.get("pct")
    if isinstance(pct, (int, float)) and pct >= 100:
        return True
    return False


def _load_job_management_steps_from_ui_state() -> list[dict[str, Any]] | None:
    """Read job_management runtime ui_state.json and derive steps from topFlow (stage-level)."""
    path = _job_management_ui_state_path()
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None

    top_flow = raw.get("topFlow")
    if not isinstance(top_flow, list) or not top_flow:
        return None

    steps: list[dict[str, Any]] = []
    for top in top_flow:
        if not isinstance(top, dict):
            continue
        top_id = str(top.get("id") or "").strip()
        top_label = str(top.get("label") or top_id or "阶段").strip()
        if not top_id:
            continue
        steps.append(
            {
                "id": f"job_management_top_{top_id}",
                "name": top_label,
                "done": _coerce_done_from_flow_item(top),
            }
        )

    return steps or None


def _overlay_job_management_steps(task_status: dict[str, Any]) -> dict[str, Any]:
    """If ui_state.json has topFlow, override job_management steps/status in task_status payload."""
    modules = task_status.get("modules")
    if not isinstance(modules, list) or not modules:
        return task_status

    steps = _load_job_management_steps_from_ui_state()
    if not steps:
        return task_status

    for module in modules:
        if not isinstance(module, dict):
            continue
        if str(module.get("id") or "") != "job_management":
            continue
        module["steps"] = steps
        done_count = sum(1 for s in steps if isinstance(s, dict) and s.get("done") is True)
        if done_count == len(steps):
            module["status"] = "completed"
        elif done_count > 0:
            module["status"] = "running"
        else:
            module["status"] = "pending"
        break

    return task_status


def _sync_job_management_task_progress_from_ui_state(raw_task_progress: dict[str, Any]) -> bool:
    """Sync job_management task_progress.json tasks from ui_state.json topFlow (stage-level).

    Returns True if the in-memory payload was modified.
    """
    if not isinstance(raw_task_progress, dict):
        return False
    progress = raw_task_progress.get("progress")
    if not isinstance(progress, list) or not progress:
        return False

    path = _job_management_ui_state_path()
    if not path.is_file():
        return False

    try:
        ui_state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(ui_state, dict):
        return False

    top_flow = ui_state.get("topFlow")
    if not isinstance(top_flow, list) or not top_flow:
        return False

    jm = None
    for m in progress:
        if isinstance(m, dict) and str(m.get("moduleId") or "") == "job_management":
            jm = m
            break
    if not isinstance(jm, dict):
        return False
    tasks = jm.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return False

    top_tasks: list[dict[str, Any]] = []
    for top in top_flow:
        if not isinstance(top, dict):
            continue
        label = str(top.get("label") or "").strip()
        if not label:
            continue
        top_tasks.append({"name": label, "completed": _coerce_done_from_flow_item(top)})
    if not top_tasks:
        return False

    # Replace job_management tasks to match topFlow exactly.
    changed = tasks != top_tasks
    if changed:
        jm["tasks"] = top_tasks

    if changed:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        raw_task_progress["updatedAt"] = ui_state.get("updatedAt") or now
        jm["updatedAt"] = ui_state.get("updatedAt") or now
    return changed


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def merge_task_progress_sync_to_disk(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge a ``task_progress.sync`` event payload into ``task_progress.json`` on disk.

    Strict, non-destructive merge:

    * Locate target module by ``moduleId``. If the module does **not** already exist in
      the on-disk ``progress[]`` list, **skip** it (do not append) — appending unknown
      modules pollutes the top stepper / overall counts.
    * Within a matched module, only update task ``completed`` flags **by index** — only
      when ``len(incoming.tasks) == len(disk.tasks)``. We never overwrite the on-disk
      task ``name`` (drivers may emit English slugs while the persisted file holds the
      Chinese display name; index-based completion update keeps both schemas valid).
    * If nothing actually changed (incoming flags match disk), **no write** happens.

    Returns a structured report so the bridge layer can emit warnings without raising.

    This function is the single seam where a ``task_progress.sync`` event becomes
    durable; ``_set_project_progress_and_emit`` already writes its own slice and is
    intentionally **not** routed through here to avoid double-writes.
    """
    report: dict[str, Any] = {
        "merged_module_ids": [],
        "skipped": [],
        "wrote_disk": False,
    }

    if not isinstance(payload, dict):
        return report
    incoming_modules = payload.get("modules")
    if not isinstance(incoming_modules, list) or not incoming_modules:
        return report

    path = task_progress_file_path()
    if path.is_file():
        try:
            disk = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report["skipped"].append({"moduleId": "*", "reason": f"disk_unreadable:{type(exc).__name__}"})
            return report
        if not isinstance(disk, dict):
            disk = default_task_progress_file_payload()
    else:
        disk = default_task_progress_file_payload()

    progress = disk.get("progress")
    if not isinstance(progress, list):
        progress = []
        disk["progress"] = progress

    by_id: dict[str, dict[str, Any]] = {}
    for entry in progress:
        if isinstance(entry, dict):
            mid = str(entry.get("moduleId") or "").strip()
            if mid:
                by_id[mid] = entry

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    changed = False
    merged: list[str] = []
    skipped: list[dict[str, str]] = report["skipped"]

    for inc in incoming_modules:
        if not isinstance(inc, dict):
            continue
        mid = str(inc.get("moduleId") or "").strip()
        if not mid:
            skipped.append({"moduleId": "", "reason": "missing_module_id"})
            continue
        target = by_id.get(mid)
        if target is None:
            skipped.append({"moduleId": mid, "reason": "not_in_disk"})
            continue
        inc_tasks = inc.get("tasks")
        tgt_tasks = target.get("tasks")
        if not isinstance(inc_tasks, list) or not isinstance(tgt_tasks, list):
            skipped.append({"moduleId": mid, "reason": "tasks_not_list"})
            continue
        if len(inc_tasks) != len(tgt_tasks):
            skipped.append(
                {
                    "moduleId": mid,
                    "reason": f"task_count_mismatch:disk={len(tgt_tasks)},incoming={len(inc_tasks)}",
                }
            )
            continue

        any_change = False
        for i, t in enumerate(tgt_tasks):
            if not isinstance(t, dict):
                continue
            inc_t = inc_tasks[i]
            if not isinstance(inc_t, dict) or "completed" not in inc_t:
                continue
            new_done = bool(inc_t.get("completed"))
            if t.get("completed") != new_done:
                t["completed"] = new_done
                any_change = True
        if any_change:
            target["updatedAt"] = now_iso
            merged.append(mid)
            changed = True

    if changed:
        disk["updatedAt"] = now_iso
        try:
            _write_json_atomic(path, disk)
            report["wrote_disk"] = True
        except OSError as exc:
            skipped.append({"moduleId": "*", "reason": f"write_failed:{type(exc).__name__}"})

    report["merged_module_ids"] = merged
    return report


def load_task_status_payload() -> dict[str, Any]:
    path = task_progress_file_path()
    if not path.is_file():
        return _overlay_job_management_steps(normalize_task_progress_payload(default_task_progress_file_payload()))
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("task_progress.json must contain a JSON object")
    # Keep persisted job_management tasks aligned with runtime ui_state.json.
    if _sync_job_management_task_progress_from_ui_state(raw):
        try:
            _write_json_atomic(path, raw)
        except OSError:
            # If disk write fails, still serve the request (best-effort sync).
            pass
    return _overlay_job_management_steps(normalize_task_progress_payload(raw))
